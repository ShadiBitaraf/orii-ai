import click
import os
import json
import hashlib
import time
import uuid
from datetime import datetime, timezone, timedelta
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI
from dotenv import load_dotenv
import redis
from functools import lru_cache
from prometheus_client import Counter, Histogram, start_http_server
from posthog import Posthog

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar",  # Full access for testing all operations
    "https://www.googleapis.com/auth/calendar.events",
]

# Initialize Redis for caching
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

# Initialize OpenAI client with Helicone
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://oai.hconeai.com/v1",
    default_headers={
        "Helicone-Auth": f"Bearer {os.getenv('HELICONE_API_KEY')}",
        "Helicone-Cache-Enabled": "true",
        "Helicone-Property-Query-Type": "calendar_assistant",
    },
)

# Cache configuration
CACHE_TTL = 300  # 5 minutes for development, adjust as needed
LLM_CACHE_SIZE = 100  # Number of LLM responses to cache in memory

# Prometheus metrics
PROM_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))

# API metrics
llm_requests_total = Counter(
    "orii_llm_requests_total", "Total number of LLM API requests", ["status", "model"]
)

llm_request_duration = Histogram(
    "orii_llm_request_duration_seconds", "Time spent processing LLM requests", ["model"]
)

calendar_requests_total = Counter(
    "orii_calendar_requests_total",
    "Total number of Google Calendar API requests",
    ["operation", "status"],
)

calendar_request_duration = Histogram(
    "orii_calendar_request_duration_seconds",
    "Time spent processing Calendar API requests",
    ["operation"],
)

cache_hits = Counter(
    "orii_cache_hits_total", "Total number of cache hits", ["cache_type"]
)

# Initialize PostHog
posthog = Posthog(
    project_api_key=os.getenv("POSTHOG_API_KEY"),
    host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
)

# Start Prometheus metrics server if not in CLI mode
if not os.getenv("CLI_MODE"):
    start_http_server(PROM_PORT)
    print(f"Prometheus metrics available on port {PROM_PORT}")


def generate_cache_key(events_text, query):
    """Generate a unique cache key for LLM queries"""
    content = f"{events_text}:{query}".encode("utf-8")
    return f"llm:response:{hashlib.sha256(content).hexdigest()}"


@lru_cache(maxsize=LLM_CACHE_SIZE)
def get_cached_llm_response(cache_key):
    """Get cached LLM response from memory cache"""
    return redis_client.get(cache_key)


def query_gpt(events_text, query, use_cache=True):
    """Enhanced GPT query function with caching and monitoring"""
    start_time = time.time()

    try:
        # Skip Redis if not available
        if use_cache and redis_client:
            try:
                # Generate cache key
                cache_key = generate_cache_key(events_text, query)

                # Check memory cache first (fastest)
                cached_response = get_cached_llm_response(cache_key)
                if cached_response:
                    cache_hits.labels(cache_type="memory").inc()
                    return json.loads(cached_response)

                # Check Redis cache
                redis_cached = redis_client.get(cache_key)
                if redis_cached:
                    cache_hits.labels(cache_type="redis").inc()
                    return json.loads(redis_cached)
            except redis.ConnectionError:
                print("Warning: Redis not available, proceeding without caching")
                use_cache = False

        # Make API call
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """You are ORII, a calendar assistant. You can help users manage their calendar by:
                    - Viewing upcoming events
                    - Creating new events
                    - Modifying existing events
                    - Deleting events
                    Be concise and helpful. When users want to make changes, confirm the action first.""",
                },
                {
                    "role": "user",
                    "content": f"Calendar events:\n{events_text}\n\nUser question: {query}",
                },
            ],
        )

        # Record successful request
        llm_requests_total.labels(status="success", model="gpt-4").inc()

        # Cache the response if Redis is available
        response_content = response.choices[0].message.content
        if use_cache and redis_client:
            try:
                cache_data = json.dumps(response_content)
                redis_client.setex(cache_key, CACHE_TTL, cache_data)
                get_cached_llm_response.cache_clear()  # Clear memory cache to prevent stale data
            except redis.ConnectionError:
                print("Warning: Could not cache response in Redis")

        return response_content

    except Exception as e:
        # Record failed request
        llm_requests_total.labels(status="error", model="gpt-4").inc()
        print(f"Error in LLM query: {str(e)}")
        raise
    finally:
        # Record request duration
        duration = time.time() - start_time
        llm_request_duration.labels(model="gpt-4").observe(duration)


style = Style.from_dict(
    {
        "prompt": "#00aa00 bold",
        "output": "#0000aa",
    }
)


def get_calendar_service():
    """Get an authorized Google Calendar service instance"""
    try:
        # Verify environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise ValueError(
                "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in environment variables"
            )

        # Create credentials configuration from environment variables
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            }
        }

        # Initialize the OAuth2 flow
        flow = InstalledAppFlow.from_client_config(
            client_config, SCOPES, redirect_uri="http://localhost"
        )

        # Run the OAuth2 flow
        creds = flow.run_local_server(
            port=0, access_type="offline", include_granted_scopes="true"
        )

        # Build and return the service
        service = build("calendar", "v3", credentials=creds)

        # Verify credentials are valid
        if not creds or not creds.valid:
            raise ValueError("Invalid or missing credentials")

        return service

    except Exception as e:
        print(f"Error in calendar service setup: {str(e)}")
        import traceback

        print("\nFull traceback:")
        print(traceback.format_exc())
        if isinstance(e, ValueError):
            print("Please check your credentials and try authenticating again")
        raise


def get_events(service):
    """Get calendar events with monitoring"""
    start_time = time.time()
    try:
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now_str,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        calendar_requests_total.labels(operation="list", status="success").inc()
        return events_result.get("items", [])
    except Exception as e:
        calendar_requests_total.labels(operation="list", status="error").inc()
        print(f"Error fetching events: {str(e)}")
        print(f"Request parameters: timeMin={now_str}")
        raise
    finally:
        duration = time.time() - start_time
        calendar_request_duration.labels(operation="list").observe(duration)


def create_event(service, summary, start_time, end_time, description=None):
    """Create calendar event with monitoring"""
    start_time_perf = time.time()
    try:
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if end_time <= start_time:
            raise ValueError("End time must be after start time")

        event = {
            "summary": summary,
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        }
        if description:
            event["description"] = description

        result = service.events().insert(calendarId="primary", body=event).execute()
        calendar_requests_total.labels(operation="create", status="success").inc()
        return result
    except Exception as e:
        calendar_requests_total.labels(operation="create", status="error").inc()
        print(f"Error creating event: {str(e)}")
        print(f"Event details: {event}")
        raise
    finally:
        duration = time.time() - start_time_perf
        calendar_request_duration.labels(operation="create").observe(duration)


def update_event(service, event_id, updates):
    """Helper function to update calendar events"""
    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    for key, value in updates.items():
        event[key] = value

    return (
        service.events()
        .update(calendarId="primary", eventId=event_id, body=event)
        .execute()
    )


def delete_event(service, event_id):
    """Helper function to delete calendar events"""
    return service.events().delete(calendarId="primary", eventId=event_id).execute()


def track_user_action(user_id, event_name, properties=None):
    """Track user actions with PostHog"""
    if not properties:
        properties = {}

    try:
        posthog.capture(distinct_id=user_id, event=event_name, properties=properties)
    except Exception as e:
        print(f"Error tracking user action: {str(e)}")


def get_user_identifier(service):
    """Get a unique identifier for the user"""
    try:
        # Try to get user email from credentials
        if hasattr(service, "_http") and hasattr(service._http, "credentials"):
            creds = service._http.credentials
            # Try different ways to get user info
            if hasattr(creds, "id_token") and creds.id_token:
                return creds.id_token.get("email", "unknown_user")
            elif hasattr(creds, "refresh_token"):
                # Use a hash of the refresh token as identifier
                return f"user_{hash(creds.refresh_token)}"

        # Fallback to anonymous user with timestamp
        return f"anonymous_user_{int(time.time())}"
    except Exception as e:
        print(f"Warning: Could not get user identifier: {str(e)}")
        return "anonymous_user"


def chat_mode():
    session = PromptSession(style=style)
    service = get_calendar_service()

    # Get user identifier safely
    user_id = get_user_identifier(service)
    session_id = str(uuid.uuid4())

    print("\n🗓️  ORII Calendar Assistant\n")

    # Track session start
    track_user_action(
        user_id=user_id,  # Using safe user identifier
        event_name="session_started",
        properties={"session_id": session_id, "mode": "chat"},
    )

    while True:
        try:
            user_input = session.prompt("You: ")

            if user_input.lower() in ["exit", "quit", "bye"]:
                # Track session end
                track_user_action(
                    user_id=user_id,
                    event_name="session_ended",
                    properties={
                        "session_id": session_id,
                        "mode": "chat",
                        "duration": time.time() - session_start_time,
                    },
                )
                print("Goodbye! 👋")
                break

            # Track user query
            track_user_action(
                user_id=user_id,
                event_name="user_query",
                properties={
                    "session_id": session_id,
                    "query_length": len(user_input),
                    "mode": "chat",
                },
            )

            events = get_events(service)
            events_text = "\n".join(
                [
                    f"{event['summary']} on {event['start'].get('dateTime', event['start'].get('date'))}"
                    for event in events
                ]
            )

            start_time = time.time()
            response = query_gpt(events_text, user_input)
            response_time = time.time() - start_time

            # Track response metrics
            track_user_action(
                user_id=user_id,
                event_name="assistant_response",
                properties={
                    "session_id": session_id,
                    "response_time": response_time,
                    "response_length": len(response),
                    "mode": "chat",
                },
            )

            print(f"\nORII: {response}\n")

        except KeyboardInterrupt:
            continue
        except EOFError:
            # Track session interruption
            track_user_action(
                user_id=user_id,
                event_name="session_interrupted",
                properties={"session_id": session_id, "mode": "chat"},
            )
            break
        except Exception as e:
            # Track errors
            track_user_action(
                user_id=user_id,
                event_name="error",
                properties={
                    "session_id": session_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "mode": "chat",
                },
            )
            raise


@click.group()
def cli():
    """ORII Calendar Assistant"""
    pass


@cli.command()
@click.argument("query")
def ask(query):
    """Ask a question about your calendar"""
    try:
        service = get_calendar_service()
        user_id = get_user_identifier(service)  # Get user identifier safely

        # Track single query
        track_user_action(
            user_id=user_id,  # Using safe user identifier
            event_name="single_query",
            properties={"query_length": len(query)},
        )

        start_time = time.time()
        events = get_events(service)
        events_text = "\n".join(
            [
                f"{event['summary']} on {event['start'].get('dateTime', event['start'].get('date'))}"
                for event in events
            ]
        )
        response = query_gpt(events_text, query)
        response_time = time.time() - start_time

        # Track response
        track_user_action(
            user_id=user_id,
            event_name="single_query_response",
            properties={
                "response_time": response_time,
                "response_length": len(response),
            },
        )

        click.echo(response)
    except Exception as e:
        # Track errors
        if "user_id" in locals():
            track_user_action(
                user_id=user_id,
                event_name="error",
                properties={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "mode": "single_query",
                },
            )
        click.echo(f"Error: {str(e)}")


@cli.command()
def chat():
    """Start chat mode"""
    chat_mode()


@cli.command()
def test_create():
    """Test creating a calendar event"""
    try:
        service = get_calendar_service()
        # Create a test event starting now and ending 1 hour later
        start = datetime.now(timezone.utc)
        end = datetime.now(timezone.utc) + timedelta(hours=1)  # Add 1 hour duration

        # Format the event properly
        event = create_event(
            service,
            "Test Event from ORII CLI",
            start,
            end,
            "This is a test event created by ORII CLI",
        )
        click.echo(f"Created test event: {event['id']}")
        click.echo(f"Start: {start.isoformat()}")
        click.echo(f"End: {end.isoformat()}")
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        if hasattr(e, "content"):
            click.echo(f"Detailed error: {e.content}")


@cli.command()
@click.argument("event_id")
def test_delete(event_id):
    """Test deleting a calendar event"""
    try:
        service = get_calendar_service()
        delete_event(service, event_id)
        click.echo(f"Deleted event: {event_id}")
    except Exception as e:
        click.echo(f"Error: {str(e)}")


@cli.command()
def test_llm():
    """Test LLM responses without calendar operations"""
    test_events = """Meeting with Team at 2024-03-23T15:00:00Z
Product Review at 2024-03-24T10:00:00Z
Client Call at 2024-03-25T14:30:00Z"""

    while True:
        try:
            query = click.prompt("Test query")
            if query.lower() in ["exit", "quit", "bye"]:
                break
            response = query_gpt(test_events, query)
            click.echo(f"\nORII: {response}\n")
        except (KeyboardInterrupt, EOFError):
            break


# Development mode configuration
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
if DEV_MODE:
    # Reduce API calls in development
    CACHE_TTL = 3600  # 1 hour cache in dev mode
    print("Running in development mode with extended caching")


if __name__ == "__main__":
    cli()
