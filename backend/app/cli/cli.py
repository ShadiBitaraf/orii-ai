"""
ORII Calendar Assistant CLI
Provides command-line interface for calendar management.
"""

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
from posthog import Posthog
from app.monitoring import (
    start_metrics_server,
    record_llm_request,
    record_calendar_request,
    record_cache_operation,
    record_user_session,
    record_user_query,
    HeliconeTracker,
    PosthogTracker,
    cache_manager,
)
from google.auth.transport.requests import Request
import re

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

# Initialize PostHog
posthog = Posthog(
    project_api_key=os.getenv("POSTHOG_API_KEY"),
    host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
)

# Start Prometheus metrics server if not in CLI mode
if not os.getenv("CLI_MODE"):
    start_metrics_server()
    print(f"Prometheus metrics available on port {PROM_PORT}")


def generate_cache_key(content):
    """Generate a unique cache key for LLM queries"""
    if isinstance(content, (list, dict)):
        content = json.dumps(content, sort_keys=True)
    content = content.encode("utf-8")
    return f"llm:response:{hashlib.sha256(content).hexdigest()}"


@lru_cache(maxsize=LLM_CACHE_SIZE)
def get_cached_llm_response(cache_key):
    """Get cached LLM response from memory cache"""
    return redis_client.get(cache_key)


def query_gpt(service, query, conversation_history=None, include_all_calendars=True):
    """Query GPT with calendar context"""
    start_time = time.time()
    try:
        # Get calendar events
        events = get_events(service, include_all_calendars)
        events_text = "\n".join(format_event_text(event) for event in events)

        # Build system prompt
        system_prompt = """You are a helpful calendar assistant with access to all visible calendars. You can help with:
1. Viewing events: You can see all events in the visible calendars for the next 7 days.
2. Creating events: You can suggest creating new events at specific times.
3. Modifying events: You can suggest changes to existing events.
4. Deleting events: You can suggest deleting events that are no longer needed.

When handling dates and times:
- Always consider the current time context when interpreting relative dates (e.g., "tomorrow", "next week").
- Be specific about dates and times in your responses.
- Format times in a clear, readable way (e.g., "2:30 PM" instead of "14:30").
- When suggesting event times, be mindful of working hours and existing commitments.

Maintain conversation context and relate short user responses to previous questions."""

        # Build messages array
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": f"Current events in the next 7 days:\n{events_text}",
            },
        ]

        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)

        # Add user query
        messages.append({"role": "user", "content": query})

        # Call OpenAI API with monitoring
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
        )

        # Record successful request
        record_llm_request("gpt-4", "success", time.time() - start_time)

        # Extract and return assistant's response
        return response.choices[0].message.content

    except Exception as e:
        # Record failed request
        record_llm_request("gpt-4", "error", time.time() - start_time)
        print(f"Error querying GPT: {str(e)}")
        raise


style = Style.from_dict(
    {
        "prompt": "#00aa00 bold",
        "output": "#0000aa",
    }
)


def get_calendar_service():
    """Get an authorized Google Calendar service instance with credential persistence"""
    try:
        # Verify environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        token_file = os.path.expanduser("~/.orii/token.json")

        if not client_id or not client_secret:
            raise ValueError(
                "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in environment variables"
            )

        creds = None

        # Create .orii directory if it doesn't exist
        os.makedirs(os.path.dirname(token_file), exist_ok=True)

        # Load existing credentials if available
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as token:
                    token_data = json.load(token)
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            except Exception as e:
                print(f"Error loading saved credentials: {str(e)}")
                # If there's an error loading credentials, we'll create new ones

        # If credentials don't exist or are invalid
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Error refreshing credentials: {str(e)}")
                    creds = None

            if not creds:
                # Create credentials configuration
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

            # Save the credentials
            try:
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
                print("Credentials saved successfully")
            except Exception as e:
                print(f"Warning: Could not save credentials: {str(e)}")

        # Build and return the service
        service = build("calendar", "v3", credentials=creds)
        return service

    except Exception as e:
        print(f"Error in calendar service setup: {str(e)}")
        import traceback

        print("\nFull traceback:")
        print(traceback.format_exc())
        if isinstance(e, ValueError):
            print("Please check your credentials and try authenticating again")
        raise


def get_events(service, include_all_calendars=True, days_range=7):
    """Get calendar events with monitoring"""
    start_time = time.time()
    try:
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = (now + timedelta(days=days_range)).strftime("%Y-%m-%dT%H:%M:%SZ")

        all_events = []

        if include_all_calendars:
            # Get list of all calendars
            calendar_list = service.calendarList().list().execute()
            # Strictly filter to only include calendars where selected=True
            calendars = [
                cal
                for cal in calendar_list.get("items", [])
                if cal.get("selected") is True  # Must be explicitly True
            ]

            if not calendars:
                print(
                    "Warning: No visible calendars found. Defaulting to primary calendar."
                )
                calendars = [{"id": "primary"}]
        else:
            # Only use primary calendar
            calendars = [{"id": "primary"}]

        # Fetch events from each calendar
        for calendar in calendars:
            try:
    events_result = (
        service.events()
        .list(
                        calendarId=calendar["id"],
                        timeMin=now_str,
                        timeMax=end_str,
                        maxResults=100,  # Increased from 10
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

                events = events_result.get("items", [])

                # Add calendar info to each event
                for event in events:
                    # Parse start and end times
                    start_time = None
                    end_time = None

                    start = event.get("start", {})
                    end = event.get("end", {})

                    try:
                        if "dateTime" in start:
                            start_time = datetime.fromisoformat(
                                start["dateTime"].replace("Z", "+00:00")
                            )
                        elif "date" in start:
                            start_time = datetime.strptime(
                                start["date"], "%Y-%m-%d"
                            ).replace(tzinfo=timezone.utc)

                        if "dateTime" in end:
                            end_time = datetime.fromisoformat(
                                end["dateTime"].replace("Z", "+00:00")
                            )
                        elif "date" in end:
                            # For all-day events, end date is exclusive, so subtract 1 second
                            end_time = (
                                datetime.strptime(end["date"], "%Y-%m-%d").replace(
                                    tzinfo=timezone.utc
                                )
                                + timedelta(days=1)
                                - timedelta(seconds=1)
                            )

                        if start_time and end_time:
                            # Convert to local timezone for consistent comparison
                            local_start = start_time.astimezone()
                            local_end = end_time.astimezone()

                            # Calculate duration in hours
                            duration = (
                                local_end - local_start
                            ).total_seconds() / 3600.0

                            event.update(
                                {
                                    "parsed_start": local_start,
                                    "parsed_end": local_end,
                                    "duration": duration,
                                    "calendarId": calendar.get("id"),
                                    "calendarName": calendar.get(
                                        "summary", "Primary Calendar"
                                    ),
                                }
                            )

                            # Add calendar color if available
                            if "backgroundColor" in calendar:
                                event["calendarColor"] = calendar["backgroundColor"]
                            all_events.append(event)

                    except (ValueError, TypeError) as e:
                        print(f"Error parsing event times: {str(e)}")
                        continue

            except Exception as cal_error:
                print(
                    f"Error fetching events from calendar {calendar.get('summary', calendar['id'])}: {str(cal_error)}"
                )
                continue

        # Sort events by start time
        all_events.sort(key=lambda x: x["parsed_start"])

        record_calendar_request("list", "success", time.time() - start_time)
        return all_events
    except Exception as e:
        record_calendar_request("list", "error", time.time() - start_time)
        print(f"Error fetching events: {str(e)}")
        print(f"Request parameters: timeMin={now_str}, timeMax={end_str}")
        raise


def create_event(service, event_details):
    """Create calendar event with comprehensive details"""
    start_time_perf = time.time()
    try:
        event = {
            "summary": event_details.get("summary"),
            "description": event_details.get("description", ""),
            "location": event_details.get("location", ""),
            "colorId": event_details.get("color_id", ""),  # Google Calendar color ID
        }

        # Handle start and end times
        if event_details.get("all_day", False):
            # All-day event
            start_date = event_details["start_date"]
            end_date = event_details.get("end_date", start_date)
            event["start"] = {
                "date": start_date,
                "timeZone": event_details.get("timezone", "UTC"),
            }
            event["end"] = {
                "date": end_date,
                "timeZone": event_details.get("timezone", "UTC"),
            }
        else:
            # Timed event
            start = event_details["start_time"]
            end = event_details["end_time"]

            # Ensure timezone is set
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)

            event["start"] = {
                "dateTime": start.isoformat(),
                "timeZone": event_details.get("timezone", "UTC"),
            }
            event["end"] = {
                "dateTime": end.isoformat(),
                "timeZone": event_details.get("timezone", "UTC"),
            }

        # Handle recurrence
        if event_details.get("recurrence"):
            event["recurrence"] = [event_details["recurrence"]]  # RRULE string

        # Handle attendees
        if event_details.get("attendees"):
            event["attendees"] = [
                {"email": email} for email in event_details["attendees"]
            ]

        # Handle conference data (Google Meet)
        if event_details.get("add_meet", False):
            event["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet_{int(time.time())}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
        elif event_details.get("meeting_link"):
            event["conferenceData"] = {
                "entryPoints": [
                    {
                        "entryPointType": "video",
                        "uri": event_details["meeting_link"],
                        "label": "Meeting Link",
                    }
                ]
            }

        # Handle attachments
        if event_details.get("attachments"):
            event["attachments"] = event_details["attachments"]

        # Handle reminders
        if event_details.get("reminders"):
            event["reminders"] = event_details["reminders"]

        # Handle visibility
        if event_details.get("visibility"):
            event["visibility"] = event_details["visibility"]

        # Create the event
        result = (
            service.events()
            .insert(
                calendarId="primary",
                body=event,
                conferenceDataVersion=1 if event_details.get("add_meet") else 0,
                sendUpdates=event_details.get("send_updates", "none"),
            )
            .execute()
        )

        record_calendar_request("create", "success", time.time() - start_time_perf)
        return result

    except Exception as e:
        record_calendar_request("create", "error", time.time() - start_time_perf)
        print(f"Error creating event: {str(e)}")
        print(f"Event details: {event}")
        raise


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


def format_event_text(event):
    """Format a single event for display"""
    try:
        summary = event.get("summary", "Untitled Event")
        calendar_name = event.get("calendarName", "Primary Calendar")
        calendar_color = event.get("calendarColor", "")

        # Use parsed times for consistent formatting
        start_time = event.get("parsed_start")
        end_time = event.get("parsed_end")

        if start_time and end_time:
            # Check if it's an all-day event
            is_all_day = (
                start_time.hour == 0
                and start_time.minute == 0
                and end_time.hour == 23
                and end_time.minute == 59
                and end_time.second == 59
            )

            if is_all_day:
                start_str = start_time.strftime("%Y-%m-%d")
                time_str = f"{start_str} (All day)"
            else:
                # Format times in local timezone
                local_start = start_time.astimezone()
                local_end = end_time.astimezone()

                # If same day, only show time for end
                if local_start.date() == local_end.date():
                    time_str = f"{local_start.strftime('%Y-%m-%d %I:%M %p')} - {local_end.strftime('%I:%M %p')}"
                else:
                    time_str = f"{local_start.strftime('%Y-%m-%d %I:%M %p')} - {local_end.strftime('%Y-%m-%d %I:%M %p')}"

            # Add duration
            duration = event.get("duration", 0)
            if duration > 0:
                time_str += f" ({duration:.1f} hours)"
        else:
            # Fallback to raw data if parsing failed
            start = event.get("start", {})
            if "dateTime" in start:
                time_str = start["dateTime"]
            elif "date" in start:
                time_str = f"{start['date']} (All day)"
            else:
                time_str = "No time specified"

        # Add additional details if available
        details = []
        if event.get("location"):
            details.append(f"Location: {event['location']}")
        if event.get("hangoutLink"):
            details.append(f"Meet: {event['hangoutLink']}")
        if calendar_color:
            details.append(f"Color: {calendar_color}")

        # Combine all information
        event_text = f"{summary} at {time_str} ({calendar_name})"
        if details:
            event_text += f" - {', '.join(details)}"

        return event_text
    except Exception as e:
        print(f"Error formatting event: {str(e)}")
        return str(event)  # Fallback to string representation


def chat_mode():
    session = PromptSession(style=style)
    service = get_calendar_service()

    # Get user identifier safely
    user_id = get_user_identifier(service)
    session_id = str(uuid.uuid4())
    conversation_history = []

    print("\n🗓️  ORII Calendar Assistant\n")

    # Track session start
    track_user_action(
        user_id=user_id,
        event_name="session_started",
        properties={"session_id": session_id, "mode": "chat"},
    )
    session_start_time = time.time()

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

            # Get events from all calendars
            events = get_events(service, include_all_calendars=True)

            # Format events text with error handling
            events_text = (
                "\n".join([format_event_text(event) for event in events])
                if events
                else "No upcoming events found"
            )

            start_time = time.time()
            response = query_gpt(service, user_input, conversation_history)
            response_time = time.time() - start_time

            # Add to conversation history
            conversation_history.extend(
                [
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": response},
                ]
            )

            # Keep conversation history at a reasonable size
            if len(conversation_history) > 10:  # Keep last 5 exchanges
                conversation_history = conversation_history[-10:]

            # Track response
            track_user_action(
                user_id=user_id,
                event_name="bot_response",
                properties={
                    "session_id": session_id,
                    "response_time": response_time,
                    "response_length": len(response),
                },
            )

            click.echo(f"\nORII: {response}\n")

        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {str(e)}")
            if hasattr(e, "content"):
                print(f"Detailed error: {e.content}")


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
        events = get_events(service, include_all_calendars=True)
        events_text = (
            "\n".join([format_event_text(event) for event in events])
            if events
            else "No upcoming events found"
        )

        response = query_gpt(service, query)
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
        # Create a test event starting now and ending 2 hours later
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=2)

        # Create event details dictionary
        event_details = {
            "summary": "Test Event from ORII CLI",
            "description": "This is a test event created by ORII CLI",
            "start_time": start,
            "end_time": end,
            "timezone": "UTC",
            "add_meet": True,  # Add a Google Meet link
            "reminders": {"useDefault": True},
        }

        # Create the event
        event = create_event(service, event_details)

        click.echo(f"Created test event: {event['id']}")
        click.echo(f"Start: {start.isoformat()}")
        click.echo(f"End: {end.isoformat()}")
        if event.get("hangoutLink"):
            click.echo(f"Meet link: {event['hangoutLink']}")
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
    """Test LLM responses with real calendar data"""
    try:
        service = get_calendar_service()
        conversation_history = []

        while True:
            try:
                query = click.prompt("Test query")
                if query.lower() in ["exit", "quit", "bye"]:
                    break

                # Add date context to query
                current_time = datetime.now().astimezone()
                date_context = (
                    f"Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
                )
                full_query = f"{date_context}\n{query}"

                response = query_gpt(service, full_query, conversation_history)
                conversation_history.extend(
                    [
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": response},
                    ]
                )

                # Keep conversation history manageable
                if len(conversation_history) > 10:
                    conversation_history = conversation_history[-10:]

                click.echo(f"\nORII: {response}\n")
            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                print(f"Error: {str(e)}")
                if hasattr(e, "content"):
                    print(f"Detailed error: {e.content}")
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        if hasattr(e, "content"):
            click.echo(f"Detailed error: {e.content}")


# Development mode configuration
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
if DEV_MODE:
    # Reduce API calls in development
    CACHE_TTL = 3600  # 1 hour cache in dev mode
    print("Running in development mode with extended caching")


if __name__ == "__main__":
    cli()
