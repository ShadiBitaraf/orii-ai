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
from functools import lru_cache, wraps
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
import pytz
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar",  # Full access for testing all operations
    "https://www.googleapis.com/auth/calendar.events",
]

# Initialize Redis for caching
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL)
    # Test connection
    redis_client.ping()
except Exception as e:
    print(f"Warning: Redis not available: {str(e)}")
    print("Operating in no-cache mode")
    redis_client = None

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
    if redis_client is None:
        return None
    try:
        return redis_client.get(cache_key)
    except Exception:
        return None


def parse_time_range(query):
    """Use NLP techniques to parse time range from a user query.

    This function analyzes a user query to determine:
    1. Whether they're searching in the past or future
    2. The appropriate range of days to look across
    3. Whether the query is asking for the "most recent" or "last" occurrence

    Returns:
        is_past (bool): Whether to search in the past
        days_range (int): Number of days to search
        reverse_chrono (bool): Whether to use reverse chronological ordering
    """
    # Default values
    is_past = False
    days_range = 7
    reverse_chrono = False

    # Lowercase the query for consistent parsing
    query_lower = query.lower()

    # Check if this is a "last/recent" type query - these are treated specially
    last_recent_patterns = [
        r"(?:when|what|where)(?:\s+\w+){0,4}\s+(?:was|is|did|had)(?:\s+\w+){0,3}\s+(?:last|most\s+recent|latest)",
        r"last\s+time\s+(?:i|we)",
        r"(?:my|our)\s+last\s+(?:\w+)",
        r"(?:last|latest|recent|previous|prior)",
    ]

    # Check if any last/recent pattern matches
    is_last_recent_query = any(
        re.search(pattern, query_lower) for pattern in last_recent_patterns
    )

    if is_last_recent_query:
        is_past = True
        reverse_chrono = True

        # For "last X" queries, we need to determine the appropriate time window
        # based on the event frequency - look for specific event types
        event_frequencies = {
            # Daily events - need shorter lookback
            "daily": ["meeting", "standup", "check-in", "call", "chat"],
            # Weekly events - medium lookback
            "weekly": ["session", "class", "workshop", "lesson", "sync", "1:1"],
            # Monthly events - longer lookback
            "monthly": [
                "appointment",
                "visit",
                "checkup",
                "review",
                "planning",
                "exam",
            ],
            # Infrequent events - very long lookback
            "infrequent": [
                "doctor",
                "therapy",
                "dentist",
                "medical",
                "consultation",
                "interview",
                "trip",
            ],
        }

        # Determine appropriate lookback period based on event type mentioned
        if any(term in query_lower for term in event_frequencies["daily"]):
            days_range = 14  # Two weeks for daily events
        elif any(term in query_lower for term in event_frequencies["weekly"]):
            days_range = 60  # ~2 months for weekly events
        elif any(term in query_lower for term in event_frequencies["monthly"]):
            days_range = 180  # ~6 months for monthly events
        elif any(term in query_lower for term in event_frequencies["infrequent"]):
            days_range = 365  # Full year for infrequent events
        else:
            # Default for last/recent queries without specific event types
            days_range = 90  # Look back 3 months by default

    # If not a last/recent query, process normally
    else:
        # Check for explicit time indicators
        past_indicators = [
            "previous",
            "ago",
            "before",
            "earlier",
            "past",
            "prior",
            "yesterday",
            "last",
        ]
        future_indicators = [
            "future",
            "upcoming",
            "next",
            "later",
            "soon",
            "tomorrow",
            "following",
        ]

        # Past vs future determination
        past_count = sum(1 for term in past_indicators if term in query_lower)
        future_count = sum(1 for term in future_indicators if term in query_lower)

        # Determine direction based on indicator counts
        if past_count > future_count:
            is_past = True
        elif future_count > past_count:
            is_past = False
        # If tied, do more specific checks
        else:
            # Check specific date patterns
            date_match = re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", query)
            if date_match:
                # Handle specific date mentioned in the query
                month, day, year = date_match.groups()
                if year is None:
                    year = datetime.now().year
                else:
                    year = int(year)
                    if year < 100:  # Handle 2-digit years
                        year += 2000

                # Parse the date into a datetime object
                try:
                    target_date = datetime(year, int(month), int(day))
                    current_date = datetime.now()

                    # Determine if the date is in the past or future
                    is_past = target_date < current_date

                    # Calculate days difference
                    days_range = (
                        abs((target_date - current_date).days) + 1
                    )  # Add 1 day buffer
                except (ValueError, TypeError):
                    # If date parsing fails, use defaults
                    pass

            # If still not determined, check for common temporal phrases
            elif "yesterday" in query_lower:
                is_past = True
                days_range = 1
            elif "tomorrow" in query_lower:
                is_past = False
                days_range = 1
            elif "last week" in query_lower:
                is_past = True
                days_range = 7
            elif "next week" in query_lower:
                is_past = False
                days_range = 7
            elif "last month" in query_lower:
                is_past = True
                days_range = 30
            elif "next month" in query_lower:
                is_past = False
                days_range = 30

        # Check for specific time ranges
        day_range_match = None

        # Check various patterns for day ranges
        patterns = [
            r"(?:past|next|last|coming|following)\s+(\d+)\s+days?",
            r"(\d+)\s+days?\s+(?:ago|from now)",
            r"within\s+(\d+)\s+days?",
            r"(\d+)\s+days?\s+(?:before|after)",
        ]

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                day_range_match = match
                break

        if day_range_match:
            try:
                days_range = int(day_range_match.group(1))

                # Determine past/future based on context
                if (
                    "ago" in query_lower
                    or "past" in query_lower
                    or "last" in query_lower
                ):
                    is_past = True
                elif (
                    "from now" in query_lower
                    or "next" in query_lower
                    or "coming" in query_lower
                ):
                    is_past = False
            except (ValueError, IndexError):
                # If parsing fails, keep using defaults
                pass

    return is_past, days_range, reverse_chrono


def safe_record(record_func, *args, **kwargs):
    """Safely call a record function without crashing the application if it fails"""
    try:
        # Make sure any duration parameter is a float
        if "duration" in kwargs and not isinstance(kwargs["duration"], float):
            try:
                kwargs["duration"] = float(kwargs["duration"])
            except (TypeError, ValueError):
                # If conversion fails, set a default value
                kwargs["duration"] = 0.0

        return record_func(*args, **kwargs)
    except Exception as e:
        print(f"Warning: Failed to record metric: {str(e)}")
        return None


def query_gpt(
    query, conversation_history=None, events=None, debug=False, use_context=True
):
    """Query GPT with calendar context"""
    # Ensure start_time is a float
    start_time_float = time.time()
    try:
        # Get current time for consistent date information
        current_time = datetime.now()
        current_time_str = current_time.strftime("%A, %B %d, %Y at %I:%M %p")

        # Check event dates to determine if we're using test/mock data
        using_test_data = False
        future_date_threshold = datetime.now() + timedelta(days=365)
        # Ensure future_date_threshold has timezone info
        local_tz = datetime.now().astimezone().tzinfo
        if future_date_threshold.tzinfo is None:
            future_date_threshold = future_date_threshold.replace(tzinfo=local_tz)

        if events and len(events) > 0:
            for event in events[:5]:  # Check first few events
                if "parsed_start" in event:
                    event_date = event["parsed_start"]

                    # Ensure event_date has timezone info for comparison
                    if event_date.tzinfo is None:
                        event_date = event_date.replace(tzinfo=local_tz)

                    try:
                        # Now compare with consistent timezone info
                        if event_date > future_date_threshold:
                            using_test_data = True
                            break
                    except TypeError:
                        # Skip this comparison if there's still an issue
                        continue

        # Build system prompt with clear date information
        system_prompt = f"""You are a helpful calendar assistant with access to all visible calendars. The current time is {current_time_str}.

{"NOTE: You are currently running with test/mock calendar data. Please use consistent dates from the calendar data rather than today's actual date." if using_test_data else ""}

You can help with:
1. Viewing events: You can see events in all visible calendars for ANY date the user mentions, whether past or future.
2. Creating events: You can suggest creating new events at specific times.
3. Modifying events: You can suggest changes to existing events.
4. Deleting events: You can suggest deleting events that are no longer needed.

When handling dates and times:
- Always answer direct questions like "what day is it today", "what's the date", or "what time is it" with the current date and time information: {current_time_str}
- For the current day or date, use the date from the "Current time" field provided in the context.
- Always consider the current time context when interpreting relative dates (e.g., "tomorrow", "next week").
- Be specific about dates and times in your responses.
- Format times in a clear, readable way (e.g., "2:30 PM" instead of "14:30").
- When suggesting event times, be mindful of working hours and existing commitments.
- You can access events for any date range the user specifies, both in the past and future.
- Queries about "last" or "latest" events (like "when was my last therapy session") automatically search up to a year in the past.
- NEVER tell the user you can't access events beyond a certain time period (e.g. 7 days). You CAN access events for ANY date they ask about.

Maintain conversation context and relate short user responses to previous questions.

IMPORTANT: You DO have access to the user's real calendars. The events below represent all events found (if any) within the specified time range."""

        # Format events for the LLM
        events_text = "No events found in the specified time range."
        if events and len(events) > 0:
            # Max 100 events to prevent token limit errors
            MAX_EVENTS_TO_SEND = 100
            if len(events) > MAX_EVENTS_TO_SEND:
                events = events[:MAX_EVENTS_TO_SEND]

            formatted_events = []
            for i, event in enumerate(events):
                try:
                    # Format each event
                    summary = event.get("summary", "Untitled Event")
                    start_time = event.get("start_time", "")
                    end_time = event.get("end_time", "")
                    location = event.get("location", "")
                    description = event.get("description", "")
                    is_all_day = event.get("is_all_day", False)

                    # Format start/end times for display
                    if is_all_day:
                        time_str = "All day event"
                    else:
                        # Format ISO datetime for display
                        try:
                            # Get start datetime
                            if isinstance(start_time, str) and start_time:
                                # Try different methods to parse the datetime string
                                try:
                                    # Try to parse using fromisoformat first
                                    start_dt = datetime.fromisoformat(
                                        start_time.replace("Z", "+00:00")
                                    )
                                except ValueError:
                                    # If that fails, try to use dateutil parser as fallback
                                    from dateutil import parser

                                    start_dt = parser.parse(start_time)
                            else:
                                # If not a string or empty, use the parsed_start value or start_dt directly
                                start_dt = (
                                    event.get("parsed_start")
                                    or event.get("start_dt")
                                    or datetime.now()
                                )

                            # Get end datetime
                            if isinstance(end_time, str) and end_time:
                                # Try different methods to parse the datetime string
                                try:
                                    # Try to parse using fromisoformat first
                                    end_dt = datetime.fromisoformat(
                                        end_time.replace("Z", "+00:00")
                                    )
                                except ValueError:
                                    # If that fails, try to use dateutil parser as fallback
                                    from dateutil import parser

                                    end_dt = parser.parse(end_time)
                            else:
                                # If not a string or empty, use the parsed_end value or end_dt directly
                                end_dt = (
                                    event.get("parsed_end")
                                    or event.get("end_dt")
                                    or (datetime.now() + timedelta(hours=1))
                                )

                            # Ensure both datetimes have valid timezone information
                            local_tz = datetime.now().astimezone().tzinfo
                            if start_dt.tzinfo is None:
                                start_dt = start_dt.replace(tzinfo=local_tz)
                            if end_dt.tzinfo is None:
                                end_dt = end_dt.replace(tzinfo=local_tz)

                            # Convert to local timezone
                            start_local = start_dt.astimezone()
                            end_local = end_dt.astimezone()

                            # Format nicely
                            time_str = f"{start_local.strftime('%a, %b %d, %Y %I:%M %p')} - {end_local.strftime('%I:%M %p')}"
                        except Exception:
                            # Fallback if parsing fails
                            time_str = "Time details unavailable"

                    # Create formatted event text
                    event_text = [f"Event: {summary}", f"Time: {time_str}"]

                    if location:
                        event_text.append(f"Location: {location}")

                    if description:
                        # Truncate long descriptions
                        short_desc = (
                            description[:200] + "..."
                            if len(description) > 200
                            else description
                        )
                        event_text.append(f"Description: {short_desc}")

                    # Add attendees if present
                    attendees = event.get("attendees", [])
                    if attendees:
                        try:
                            attendee_names = [
                                a.get("name", a.get("email", "Unknown"))
                                for a in attendees[:5]
                            ]
                            if len(attendees) > 5:
                                attendee_str = (
                                    ", ".join(attendee_names)
                                    + f" and {len(attendees) - 5} more"
                                )
                            else:
                                attendee_str = ", ".join(attendee_names)
                            event_text.append(f"Attendees: {attendee_str}")
                        except Exception:
                            # Skip attendees if there's an error
                            pass

                    formatted_events.append("\n".join(event_text))
                except Exception:
                    try:
                        # Fallback with minimal info
                        summary = event.get("summary", "Untitled Event")
                        event_text = [f"Event: {summary}", "Time: Details unavailable"]
                        formatted_events.append("\n".join(event_text))
                    except:
                        # Skip completely if we can't even do the fallback
                        continue

            events_text = "\n\n".join(formatted_events)

        # Build messages array
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Include event context if requested
        if use_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Events in the requested time range:\n{events_text}",
                }
            )

        # Add conversation history if provided
        if conversation_history:
            messages.extend(conversation_history)

        # Add user query
        messages.append({"role": "user", "content": query})

        # Print debug info only if debug flag is set
        if debug:
            print("\nDEBUG - Sending to GPT:")
            for msg in messages:
                print(f"[{msg['role']}] {msg['content'][:100]}...")

        # Call OpenAI API with monitoring
        try:
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )

            # Record successful request with correct duration calculation
            duration = time.time() - start_time_float

            safe_record(
                record_llm_request,
                status="success",
                model="gpt-4",
                duration=duration,
            )

            # Extract assistant's response
            assistant_response = response.choices[0].message.content

            # Return assistant's response
            return assistant_response
        except Exception as e:
            raise

    except Exception as e:
        # Record failed request with correct duration calculation
        duration = time.time() - start_time_float

        record_llm_request(
            status="error",
            model="gpt-4",
            duration=duration,
        )
        print(f"Error querying GPT: {str(e)}")
        if debug:
            import traceback

            print(traceback.format_exc())
        return f"Sorry, I encountered an error processing your request: {str(e)}"


style = Style.from_dict(
    {
        "prompt": "#00aa00 bold",
        "output": "#0000aa",
    }
)


# Global service cache with TTL
_service_cache = {"service": None, "timestamp": 0, "ttl": 3600}  # 1 hour TTL by default


def with_calendar_cache(ttl=300):
    """
    Decorator to cache results of calendar API calls with TTL.

    Args:
        ttl: Time-to-live for the cache in seconds (default: 5 minutes)
    """

    def decorator(func):
        # Use cache dictionary to store results with timestamps
        cache = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from the function name and arguments
            key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"

            # Check if we have a cached result and if it's still valid
            if key in cache:
                timestamp, result = cache[key]
                if time.time() - timestamp < ttl:
                    safe_record(record_cache_operation, "hit", func.__name__)
                    return result

            # Call the original function if no cache hit
            result = func(*args, **kwargs)

            # Cache the result with the current timestamp
            cache[key] = (time.time(), result)
            safe_record(record_cache_operation, "miss", func.__name__)

            return result

        return wrapper

    return decorator


def get_calendar_service(force_refresh=False):
    """Get an authorized Google Calendar service instance with credential persistence and caching

    Args:
        force_refresh: Force a fresh service instance even if cached (default: False)

    Returns:
        Google Calendar service instance
    """
    global _service_cache

    # Check if we have a cached service that's still valid
    current_time = time.time()
    if (
        not force_refresh
        and _service_cache["service"]
        and current_time - _service_cache["timestamp"] < _service_cache["ttl"]
    ):
        # Use cached service silently
        safe_record(record_cache_operation, "hit", "calendar_service")
        return _service_cache["service"]

    try:
        # Verify environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        token_file = os.path.expanduser("~/.orii/token.json")

        if not client_id or not client_secret:
            print("ERROR: Missing Google API credentials in environment")
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
            except json.JSONDecodeError as e:
                print(f"Error: Token file contains invalid JSON: {str(e)}")
            except Exception:
                # If there's an error loading credentials, we'll create new ones
                pass

        # If credentials don't exist or are invalid
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
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
                print("Opening browser for Google authentication...")
                creds = flow.run_local_server(
                    port=0, access_type="offline", include_granted_scopes="true"
                )

            # Save the credentials
            try:
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
            except Exception:
                # Continue even if we can't save credentials
                pass

        # Build and return the service
        service = build("calendar", "v3", credentials=creds)

        # Verify service is working by making a simple API call
        try:
            # List available calendars as a test
            calendar_list = service.calendarList().list(maxResults=10).execute()
            calendars = calendar_list.get("items", [])
        except Exception as e:
            print(f"WARNING: Calendar API test request failed: {str(e)}")

        # Cache the service
        _service_cache["service"] = service
        _service_cache["timestamp"] = current_time
        safe_record(record_cache_operation, "miss", "calendar_service")

        return service

    except Exception as e:
        print(f"Error in calendar service setup: {str(e)}")
        import traceback

        print("\nFull traceback:")
        print(traceback.format_exc())
        if isinstance(e, ValueError):
            print("Please check your credentials and try authenticating again")
        raise


@with_calendar_cache(ttl=300)  # Cache calendar list for 5 minutes
def get_calendar_list(service):
    """Get the list of calendars with caching to reduce API calls

    Args:
        service: Google Calendar service

    Returns:
        List of calendars from the Calendar API
    """
    calendar_list = service.calendarList().list().execute()
    return calendar_list.get("items", [])


def get_events(is_past, days_range, search_terms=None, reverse_chronological=False):
    """Get calendar events based on specified parameters.

    Args:
        is_past: Boolean indicating if we're searching in the past
        days_range: Number of days to search
        search_terms: Optional search terms to filter events
        reverse_chronological: Order events from newest to oldest (for "last/recent" queries)

    Returns:
        List of event objects
    """
    # Ensure days_range is an integer
    if not isinstance(days_range, int):
        try:
            days_range = int(days_range)
        except (ValueError, TypeError):
            days_range = 7

    try:
        # Get calendar service
        service = get_calendar_service()

        # Calculate time range
        now = datetime.utcnow().isoformat() + "Z"

        if is_past:
            # Search in the past up to days_range days ago
            time_min = (
                datetime.utcnow() - timedelta(days=days_range)
            ).isoformat() + "Z"
            time_max = now
        else:
            # Search in the future up to days_range days ahead
            time_min = now
            time_max = (
                datetime.utcnow() + timedelta(days=days_range)
            ).isoformat() + "Z"

        # Fetch primary calendar events
        calendar_id = "primary"

        # Prepare query parameters
        query_params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "maxResults": 2500,  # Get a large number to ensure we don't miss anything
        }

        # Set order based on search direction
        if reverse_chronological:
            # For "last" queries, we want newest events first
            query_params["orderBy"] = "startTime" if not is_past else "startTime"
            # We'll handle reverse sorting after fetching since the API doesn't support descending order
        else:
            # Default case - chronological order
            query_params["orderBy"] = "startTime"

        # Add search terms if provided
        if search_terms:
            query_params["q"] = search_terms

        events_result = service.events().list(**query_params).execute()
        events = events_result.get("items", [])

        # Process and format events
        processed_events = []
        for event in events:
            # Skip cancelled events
            if event.get("status") == "cancelled":
                continue

            # Extract event details
            event_id = event.get("id", "")
            summary = event.get("summary", "Untitled Event")
            description = event.get("description", "")
            location = event.get("location", "")
            organizer = event.get("organizer", {}).get("email", "")

            # Extract start and end times
            start = event.get("start", {})
            end = event.get("end", {})

            # Handle all-day events vs. timed events
            if "date" in start:  # All-day event
                start_time = start.get("date", "")
                end_time = end.get("date", "")
                is_all_day = True

                # Parse timestamps for sorting
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
            else:  # Timed event
                start_time = start.get("dateTime", "")
                end_time = end.get("dateTime", "")
                is_all_day = False

                # Parse timestamps for sorting
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            # Parse attendees
            attendees = []
            for attendee in event.get("attendees", []):
                attendee_email = attendee.get("email", "")
                attendee_name = attendee.get("displayName", attendee_email)
                response_status = attendee.get("responseStatus", "")

                attendees.append(
                    {
                        "email": attendee_email,
                        "name": attendee_name,
                        "response_status": response_status,
                    }
                )

            # Create processed event object
            processed_event = {
                "id": event_id,
                "summary": summary,
                "description": description,
                "location": location,
                "organizer": organizer,
                "start_time": start_time,
                "end_time": end_time,
                "is_all_day": is_all_day,
                "attendees": attendees,
                # Add calendar ID for filtering
                "calendarId": calendar_id,
                # Add timestamps for sorting
                "start_dt": start_dt,
                "end_dt": end_dt,
                # Add parsed datetime objects for easier access
                "parsed_start": start_dt,
                "parsed_end": end_dt,
                # Include original event data for reference
                "raw_event": event,
            }

            processed_events.append(processed_event)

        # Apply reverse chronological sorting if requested (for "last" queries)
        if reverse_chronological and is_past:
            processed_events.sort(key=lambda e: e["start_dt"], reverse=True)

        return processed_events

    except Exception as e:
        print(f"Error fetching events: {str(e)}")
        if hasattr(e, "content"):
            print(f"Detailed error: {e.content}")
        return []


@with_calendar_cache(ttl=3600)  # Cache timezone for 1 hour
def get_calendar_timezone(service, calendar_id):
    """Get the timezone for a specific calendar with caching

    Args:
        service: Google Calendar service
        calendar_id: ID of the calendar

    Returns:
        Timezone string or None if not found
    """
    try:
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        return calendar.get("timeZone")
    except Exception as e:
        print(f"Warning: Could not retrieve calendar timezone: {str(e)}")
        return None


def create_event(service, event_details, calendar_id="primary"):
    """Create calendar event with comprehensive details"""
    start_time_perf = time.time()
    try:
        # Get user's timezone setting from the calendar using the cached function
        user_timezone = get_calendar_timezone(service, calendar_id)
        if not user_timezone:
            # Will fall back to local timezone
            pass

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

            # Use user timezone for all-day events if available
            timezone_to_use = user_timezone or event_details.get("timezone") or "UTC"

            event["start"] = {
                "date": start_date,
                "timeZone": timezone_to_use,
            }
            event["end"] = {
                "date": end_date,
                "timeZone": timezone_to_use,
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

            # Use user timezone if available, otherwise use event timezone or fall back to local
            timezone_to_use = (
                user_timezone
                or event_details.get("timezone")
                or start.tzinfo.tzname(None)
            )

            event["start"] = {
                "dateTime": start.isoformat(),
                "timeZone": timezone_to_use,
            }
            event["end"] = {
                "dateTime": end.isoformat(),
                "timeZone": timezone_to_use,
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
                calendarId=calendar_id,
                body=event,
                conferenceDataVersion=1 if event_details.get("add_meet") else 0,
                sendUpdates=event_details.get("send_updates", "none"),
            )
            .execute()
        )

        safe_record(
            record_calendar_request, "create", "success", time.time() - start_time_perf
        )
        return result

    except Exception as e:
        safe_record(
            record_calendar_request, "create", "error", time.time() - start_time_perf
        )
        print(f"Error creating event: {str(e)}")
        raise


def update_event(service, event_id, updates, calendar_id="primary"):
    """Update an existing calendar event

    Args:
        service: Google Calendar service
        event_id: ID of the event to update
        updates: Dictionary of updates to apply to the event
        calendar_id: ID of the calendar containing the event (default: primary)

    Returns:
        Updated event object
    """
    try:
        # Use the existing event as the base
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Apply the updates
        for key, value in updates.items():
            event[key] = value

        # Update the event
        updated_event = (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event)
            .execute()
        )

        safe_record(record_calendar_request, "update", "success", 0)
        return updated_event
    except Exception as e:
        safe_record(record_calendar_request, "update", "error", 0)
        raise


def delete_event(service, event_id, calendar_id="primary"):
    """Helper function to delete calendar events

    Args:
        service: Google Calendar service
        event_id: ID of the event to delete
        calendar_id: ID of the calendar containing the event (default: primary)

    Returns:
        API response from deletion request
    """
    try:
        result = (
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        )
        safe_record(record_calendar_request, "delete", "success", 0)
        return result
    except Exception as e:
        safe_record(record_calendar_request, "delete", "error", 0)
        raise


def track_user_action(user_id, event_name, properties=None):
    """Track user actions with PostHog"""
    if not properties:
        properties = {}

    try:
        posthog.capture(distinct_id=user_id, event=event_name, properties=properties)
    except Exception as e:
        print(f"Warning: Error tracking user action: {str(e)}")
        # Continue execution even if tracking fails


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
    except Exception:
        # Silently return basic string representation on error
        return str(event)  # Fallback to string representation


def chat_mode(include_all_calendars=True):
    session = PromptSession(style=style)
    service = get_calendar_service()

    # Get user identifier safely
    user_id = get_user_identifier(service)
    session_id = str(uuid.uuid4())
    conversation_history = []

    print("\n🗓️  ORII Calendar Assistant\n")
    print(
        "I can search through your calendars, looking at both past and future events."
    )
    print("I can also create and delete events directly.")
    print("To exit, type 'exit', 'quit', or 'bye'.\n")

    # Track session start
    track_user_action(
        user_id=user_id,
        event_name="session_started",
        properties={"session_id": session_id, "mode": "chat"},
    )
    session_start_time = time.time()

    try:
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

                # First, check if this is an event creation request
                creation_details = parse_event_creation_details(user_input)
                if creation_details:
                    # Handle event creation directly without using LLM
                    try:
                        # Check if a specific calendar was mentioned
                        calendar_id = "primary"
                        if "calendar_name" in creation_details:
                            specific_cal_id = extract_calendar_id(
                                service, creation_details["calendar_name"], user_id
                            )
                            if specific_cal_id:
                                calendar_id = specific_cal_id

                        # Create the event
                        event = create_event(service, creation_details, calendar_id)

                        # Format response
                        start_time = creation_details["start_time"].strftime("%I:%M %p")
                        end_time = creation_details["end_time"].strftime("%I:%M %p")
                        date_str = creation_details["start_time"].strftime(
                            "%A, %B %d, %Y"
                        )

                        response = f"Created event: '{creation_details['summary']}' on {date_str} from {start_time} to {end_time}"

                        if "location" in creation_details:
                            response += f" at {creation_details['location']}"

                        if (
                            "add_meet" in creation_details
                            and creation_details["add_meet"]
                        ):
                            if event.get("hangoutLink"):
                                response += f"\nMeet link: {event['hangoutLink']}"

                        # Add to conversation history
                        conversation_history.extend(
                            [
                                {"role": "user", "content": user_input},
                                {"role": "assistant", "content": response},
                            ]
                        )

                        click.echo(f"\nORII: {response}\n")
                        continue  # Skip LLM call
                    except Exception as e:
                        error_msg = f"Sorry, I couldn't create that event: {str(e)}"
                        conversation_history.extend(
                            [
                                {"role": "user", "content": user_input},
                                {"role": "assistant", "content": error_msg},
                            ]
                        )
                        click.echo(f"\nORII: {error_msg}\n")
                        continue  # Skip LLM call

                # Handle calendar-specific query and LLM
                specific_calendar_id = None
                calendar_match = re.search(
                    r"(?:in|on|from)\s+(?:my\s+)?(?:the\s+)?([a-zA-Z0-9\s]+?)\s+calendar",
                    user_input,
                    re.IGNORECASE,
                )
                if calendar_match:
                    calendar_name = calendar_match.group(1).strip()
                    specific_calendar_id = extract_calendar_id(
                        service, calendar_name, user_id
                    )

                # Basic time/date queries that don't need LLM
                basic_time_patterns = [
                    r"^\s*(?:what|tell me)?\s*(?:(?:is|about|current)\s+)?(?:the\s+)?(?:date|day|time)\s+(?:today|now|right now|is it)?\s*\??$",
                    r"^\s*(?:what|which)\s+day\s+(?:of the week|is it today|is today)\s*\??$",
                    r"^\s*(?:what|what's)\s+today\??$",
                ]

                is_basic_time_query = any(
                    re.match(pattern, user_input.lower())
                    for pattern in basic_time_patterns
                )

                if is_basic_time_query:
                    # Always provide accurate real-world time for direct time queries
                    now = datetime.now()
                    weekday = now.strftime("%A")
                    date = now.strftime("%B %d, %Y")
                    time_str = now.strftime("%I:%M %p")

                    response = (
                        f"Today is {weekday}, {date}. The current time is {time_str}."
                    )

                    # Add to conversation history
                    conversation_history.extend(
                        [
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": response},
                        ]
                    )

                    click.echo(f"\nORII: {response}\n")
                    continue  # Skip LLM call

                # Check for test/mock data disclaimer needed
                # This detects queries about specific dates that might not match real dates
                date_related_query = any(
                    term in user_input.lower()
                    for term in [
                        "today",
                        "tomorrow",
                        "yesterday",
                        "next week",
                        "last week",
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    ]
                )

                try:
                    # Start measuring response time with a different variable name
                    query_start_time = time.time()

                    # Parse time range to determine if we're looking in past or future
                    is_past, days_range, reverse_chrono = parse_time_range(user_input)

                    # Get relevant events
                    search_terms = None
                    if "extract_search_terms" in globals():
                        search_terms = extract_search_terms(user_input)
                    events = get_events(
                        is_past, days_range, search_terms, reverse_chrono
                    )

                    # Generate response using LLM for general queries
                    if specific_calendar_id:
                        # Only search in the specified calendar - filter events by calendar ID
                        filtered_events = [
                            e
                            for e in events
                            if e.get("calendarId", "primary") == specific_calendar_id
                        ]
                        response = query_gpt(
                            user_input,
                            conversation_history,
                            filtered_events,
                            debug=False,
                            use_context=True,
                        )
                    else:
                        # Use all events
                        response = query_gpt(
                            user_input,
                            conversation_history,
                            events,
                            debug=False,
                            use_context=True,
                        )

                    # If using test data and query is date-related, append a note to the response
                    if date_related_query:
                        # Check if any event has date far in the future/past
                        using_test_data = False
                        future_date_threshold = datetime.now() + timedelta(days=365)
                        # Ensure future_date_threshold has timezone info
                        local_tz = datetime.now().astimezone().tzinfo
                        if future_date_threshold.tzinfo is None:
                            future_date_threshold = future_date_threshold.replace(
                                tzinfo=local_tz
                            )

                        if events and len(events) > 0:
                            for event in events[:5]:  # Check first few events
                                if "parsed_start" in event:
                                    event_date = event["parsed_start"]

                                    # Ensure event_date has timezone info for comparison
                                    if event_date.tzinfo is None:
                                        event_date = event_date.replace(tzinfo=local_tz)

                                    try:
                                        if event_date > future_date_threshold:
                                            using_test_data = True
                                            break
                                    except TypeError:
                                        # Skip this comparison if there's still an issue
                                        continue

                        if (
                            using_test_data
                            and "NOTE: This is test data" not in response
                        ):
                            response += "\n\nNOTE: This is test calendar data. Date references might not match the current real-world date."

                    # Calculate response time using our renamed variable
                    response_time = time.time() - query_start_time
                    print(f"DEBUG - Total response time: {response_time} seconds")

                    # Track response
                    track_user_action(
                        user_id=user_id,
                        event_name="single_query_response",
                        properties={
                            "response_time": response_time,
                            "response_length": len(response),
                        },
                    )

                    # Update conversation history
                    conversation_history.extend(
                        [
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": response},
                        ]
                    )

                    # Keep conversation history manageable
                    if len(conversation_history) > 10:
                        conversation_history = conversation_history[-10:]

                    click.echo(f"\nORII: {response}\n")
                except Exception as e:
                    # Track errors
                    if user_id:
                        track_user_action(
                            user_id=user_id,
                            event_name="query_error",
                            properties={
                                "error_type": str(type(e)),
                                "error_message": str(e),
                            },
                        )
                    click.echo(f"Error: {str(e)}")
                    if hasattr(e, "content"):
                        click.echo(f"Detailed error: {e.content}")

                    # Try to give a more helpful error message for token limit errors
                    if "too large" in str(e).lower() or "token" in str(e).lower():
                        click.echo(
                            "\nTry asking about a smaller date range or being more specific in your query."
                        )
                    # Try to provide a basic response for time/date questions even if API fails
                    elif any(
                        kw in user_input.lower()
                        for kw in ["time", "date", "day", "today"]
                    ):
                        now = datetime.now()
                        basic_response = f"Today is {now.strftime('%A, %B %d, %Y')}. The current time is {now.strftime('%I:%M %p')}."
                        click.echo(f"\nORII: {basic_response}\n")

                        # Add to conversation history
                        conversation_history.extend(
                            [
                                {"role": "user", "content": user_input},
                                {"role": "assistant", "content": basic_response},
                            ]
                        )
            except (KeyboardInterrupt, EOFError):
                print("\nSession interrupted. Goodbye! 👋")
                break
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        print("Please try again or restart the application.")


# Development mode configuration
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
if DEV_MODE:
    # Reduce API calls in development
    CACHE_TTL = 3600  # 1 hour cache in dev mode
    print("Running in development mode with extended caching")


def extract_calendar_id(service, calendar_name, user_id=None):
    """Extract calendar ID from a name or partial name mention

    Args:
        service: Google Calendar service
        calendar_name: Name or partial name of the calendar
        user_id: Optional user ID for tracking

    Returns:
        Calendar ID if found, None otherwise
    """
    try:
        if not calendar_name:
            return None

        # Standardize the input
        calendar_name = calendar_name.lower().strip()

        # Get list of calendars using the cached function
        calendars = get_calendar_list(service)

        # Look for exact or partial matches
        matched_calendars = []
        for cal in calendars:
            if cal.get("selected") is not True:
                continue

            cal_summary = cal.get("summary", "").lower()
            if calendar_name == cal_summary:
                # Exact match
                return cal.get("id")
            elif calendar_name in cal_summary:
                # Partial match
                matched_calendars.append((cal.get("id"), cal.get("summary")))

        # If no exact match but one partial match
        if len(matched_calendars) == 1:
            return matched_calendars[0][0]

        # Multiple matches or no matches
        return None
    except Exception as e:
        print(f"Error extracting calendar ID: {str(e)}")
        if user_id:
            track_user_action(
                user_id=user_id,
                event_name="calendar_extraction_error",
                properties={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
        return None


@with_calendar_cache(ttl=60)  # Cache event list responses for 60 seconds
def fetch_events(service, query_params):
    """Fetch events from a calendar with caching

    Args:
        service: Google Calendar service
        query_params: Dictionary of query parameters for the API call

    Returns:
        List of events from the Calendar API
    """
    events_result = service.events().list(**query_params).execute()
    return events_result.get("items", [])


def parse_event_creation_details(query):
    """Parse event creation details from user query

    Returns:
        Dict with event details if found, None otherwise
    """
    event_details = {}

    # Check if this is an event creation request
    creation_indicators = [
        "create event",
        "add event",
        "new event",
        "schedule",
        "plan",
        "book",
        "set up",
        "add to calendar",
        "create a meeting",
    ]

    is_creation_request = any(
        indicator in query.lower() for indicator in creation_indicators
    )
    if not is_creation_request:
        return None

    # Extract event title/summary - look for common patterns
    title_patterns = [
        r'(?:called|titled|named|for|about)\s+"([^"]+)"',
        r"(?:called|titled|named|for|about)\s+\'([^\']+)\'",
        r"(?:called|titled|named|for|about)\s+([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+from|\s+\.|$)",
        r"create\s+(?:an\s+)?event\s+(?:called\s+)?([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+from|\s+\.|$)",
    ]

    for pattern in title_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            event_details["summary"] = match.group(1).strip()
            break

    if "summary" not in event_details:
        # Default title if we can't extract one
        event_details["summary"] = "New Event"

    # Use the improved datetime parser for all date/time extraction
    datetime_info = parse_natural_language_datetime(
        query, default_days=1, default_duration_hours=1
    )

    if datetime_info["is_all_day"]:
        # Handle all-day event
        event_details["all_day"] = True
        event_details["start_date"] = datetime_info["start_datetime"].strftime(
            "%Y-%m-%d"
        )
        # For all-day events, end_date should be the same as start_date unless specified
        event_details["end_date"] = datetime_info["end_datetime"].strftime("%Y-%m-%d")
    else:
        # Regular timed event
        event_details["start_time"] = datetime_info["start_datetime"]
        event_details["end_time"] = datetime_info["end_datetime"]
        event_details["timezone"] = str(datetime_info["start_datetime"].tzinfo)

    # Look for location
    location_match = re.search(
        r"(?:at|in)\s+(?:the\s+)?(?:location\s+)?([^,.]+)(?:\.|,|$)",
        query,
        re.IGNORECASE,
    )
    if location_match:
        event_details["location"] = location_match.group(1).strip()

    # Look for attendees
    attendees_match = re.search(
        r"(?:with|invite)\s+([^,.]+)(?:\.|,|$)", query, re.IGNORECASE
    )
    if attendees_match:
        # This is simplified - in a real app, you would want to validate these as email addresses
        attendees_str = attendees_match.group(1).strip()
        attendees = [a.strip() for a in re.split(r"(?:,|\s+and\s+)", attendees_str)]
        if attendees:
            event_details["attendees"] = attendees

    # Check for Google Meet
    if "meet" in query.lower() or "video" in query.lower() or "call" in query.lower():
        event_details["add_meet"] = True

    # Check for specific calendar mention
    calendar_match = re.search(
        r"(?:in|on|to)\s+(?:my\s+)?(?:the\s+)?([a-zA-Z0-9\s]+?)\s+calendar",
        query,
        re.IGNORECASE,
    )
    if calendar_match:
        event_details["calendar_name"] = calendar_match.group(1).strip()

    return event_details


def parse_event_deletion_details(query):
    """Parse event deletion details from user query with enhanced detail extraction

    Returns:
        Dict with deletion criteria if found, None otherwise
    """
    deletion_details = {}

    # Check if this is a deletion request
    deletion_indicators = [
        "delete event",
        "remove event",
        "cancel event",
        "delete meeting",
        "remove meeting",
        "cancel meeting",
        "delete appointment",
        "remove appointment",
        "cancel appointment",
        "remove the",
        "cancel the",
        "delete the",
    ]

    is_deletion_request = any(
        indicator in query.lower() for indicator in deletion_indicators
    )
    if not is_deletion_request:
        return None

    # Extract event title/summary for matching
    title_patterns = [
        r'(?:called|titled|named)\s+"([^"]+)"',
        r"(?:called|titled|named)\s+\'([^\']+)\'",
        r"(?:delete|remove|cancel)(?:\s+the)?\s+(?:event|meeting|appointment|call)?\s+(?:titled|called|named)?\s*"
        r'"([^"]+)"',
        r"(?:delete|remove|cancel)(?:\s+the)?\s+(?:event|meeting|appointment|call)?\s+(?:titled|called|named)?\s*"
        r"\'([^\']+)\'",
        r"(?:delete|remove|cancel)(?:\s+the)?\s+(?:event|meeting|appointment|call)?\s+(?:titled|called|named)?\s+"
        r"([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+from|\s+with|\s+\.|$|\s+because|\s+that|\s+which)",
    ]

    for pattern in title_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            deletion_details["event_title"] = match.group(1).strip()
            break

    # Extract additional descriptive details that might help identify the event
    detail_patterns = [
        r"(?:with|involving|for|about)\s+([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+\.|$)",
        r"(?:regarding|related to|concerning)\s+([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+\.|$)",
    ]

    event_details = []
    for pattern in detail_patterns:
        matches = re.finditer(pattern, query, re.IGNORECASE)
        for match in matches:
            event_details.append(match.group(1).strip())

    if event_details:
        deletion_details["event_details"] = event_details

    # Use the improved natural language datetime parser
    datetime_info = parse_natural_language_datetime(query, default_days=7)

    # If we have date information, add it to deletion details
    if datetime_info["date_specified"]:
        deletion_details["date_str"] = datetime_info["start_datetime"].strftime(
            "%Y-%m-%d"
        )

    # If we have time information, add it to deletion details
    if datetime_info["time_specified"]:
        deletion_details["time_str"] = datetime_info["start_datetime"].strftime(
            "%I:%M %p"
        )

        # Determine time period based on hour
        hour = datetime_info["start_datetime"].hour
        if 5 <= hour <= 11:
            deletion_details["time_period"] = "morning"
        elif 12 <= hour <= 16:
            deletion_details["time_period"] = "afternoon"
        elif 17 <= hour <= 20:
            deletion_details["time_period"] = "evening"
        else:  # 21-4
            deletion_details["time_period"] = "night"

    # Check for specific calendar mention
    calendar_match = re.search(
        r"(?:from|in|on)\s+(?:my\s+)?(?:the\s+)?([a-zA-Z0-9\s]+?)\s+calendar",
        query,
        re.IGNORECASE,
    )
    if calendar_match:
        deletion_details["calendar_name"] = calendar_match.group(1).strip()

    # Look for people involved in the event
    people_match = re.search(
        r"(?:with|involving)\s+([a-zA-Z0-9\s,]+?)(?:\s+on|\s+at|\s+\.|$)",
        query,
        re.IGNORECASE,
    )
    if people_match:
        people_str = people_match.group(1).strip()
        people = [p.strip() for p in re.split(r"(?:,|\s+and\s+)", people_str)]
        if people:
            deletion_details["people"] = people

    # Look for location information
    location_match = re.search(
        r"(?:at|in)\s+(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+\.|$)",
        query,
        re.IGNORECASE,
    )
    if location_match and "calendar" not in location_match.group(1).lower():
        deletion_details["location"] = location_match.group(1).strip()

    # Set the search range in days
    days_range = 7  # Default to 1 week
    if datetime_info["date_specified"]:
        # Calculate days difference from today to the specified date
        today = datetime.now().date()
        target_date = datetime_info["start_datetime"].date()
        days_diff = abs((target_date - today).days)

        # Add a buffer of 1 day to ensure we capture the event
        days_range = max(days_diff + 1, 1)

    deletion_details["days_range"] = days_range

    # Determine if we're looking in the past or future
    if datetime_info["date_specified"]:
        today = datetime.now().date()
        target_date = datetime_info["start_datetime"].date()
        deletion_details["search_past"] = target_date < today
    else:
        # Check for past indicators in the query
        past_indicators = ["past", "previous", "earlier", "before", "last", "yesterday"]
        deletion_details["search_past"] = any(
            indicator in query.lower() for indicator in past_indicators
        )

    return deletion_details


def parse_natural_language_datetime(text, default_days=7, default_duration_hours=1):
    """
    Parse natural language date/time from text using dateutil's parser with enhanced context.

    Args:
        text: The text containing date/time information
        default_days: Default number of days to look ahead if no specific date found
        default_duration_hours: Default duration for events in hours

    Returns:
        Dictionary with extracted date and time information
    """
    result = {
        "start_datetime": None,
        "end_datetime": None,
        "is_all_day": False,
        "date_specified": False,
        "time_specified": False,
        "duration_specified": False,
        "duration_hours": default_duration_hours,
    }

    if not text:
        return result

    # Use current date/time as the default
    base_time = datetime.now()

    # Common time expressions
    time_range_patterns = [
        r"from\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+to\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
    ]

    # Duration patterns
    duration_patterns = [
        r"for\s+(\d+)\s+hour",
        r"for\s+(\d+)\s+minute",
        r"(\d+)\s+hour\s+(?:long|duration)",
        r"(\d+)\s+minute\s+(?:long|duration)",
    ]

    # Special date handling for common terms
    if re.search(r"\b(today|tonight)\b", text, re.IGNORECASE):
        result["start_datetime"] = base_time
        result["date_specified"] = True

    elif re.search(r"\btomorrow\b", text, re.IGNORECASE):
        result["start_datetime"] = base_time + timedelta(days=1)
        result["date_specified"] = True

    elif re.search(r"\bin\s+(\d+)\s+days?\b", text, re.IGNORECASE):
        days_match = re.search(r"\bin\s+(\d+)\s+days?\b", text, re.IGNORECASE)
        if days_match:
            days = int(days_match.group(1))
            result["start_datetime"] = base_time + timedelta(days=days)
            result["date_specified"] = True

    elif re.search(r"\bnext\s+(week|month)\b", text, re.IGNORECASE):
        unit_match = re.search(r"\bnext\s+(week|month)\b", text, re.IGNORECASE)
        if unit_match:
            unit = unit_match.group(1).lower()
            if unit == "week":
                result["start_datetime"] = base_time + timedelta(days=7)
            else:  # month
                result["start_datetime"] = base_time + relativedelta(months=1)
            result["date_specified"] = True

    # Check for specific weekdays
    weekday_match = re.search(
        r"\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        text,
        re.IGNORECASE,
    )
    if weekday_match:
        is_next = weekday_match.group(1) is not None
        day_name = weekday_match.group(2).lower()
        day_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_day = day_map[day_name]
        days_ahead = target_day - base_time.weekday()

        if (
            days_ahead <= 0 or is_next
        ):  # If the day has passed this week or specifically "next"
            days_ahead += 7

        result["start_datetime"] = base_time + timedelta(days=days_ahead)
        result["date_specified"] = True

    # If we haven't set a date yet, try to use dateutil parser
    if not result["date_specified"]:
        try:
            # Try to extract a date using dateutil parser
            parsed_date = date_parser.parse(text, fuzzy=True, default=base_time)

            # Only accept the date if it's not just returning the default (today)
            if parsed_date.date() != base_time.date() or "today" in text.lower():
                result["start_datetime"] = parsed_date
                result["date_specified"] = True
        except:
            # If parsing fails, don't set any date
            pass

    # Check for time range expressions
    for pattern in time_range_patterns:
        time_match = re.search(pattern, text, re.IGNORECASE)
        if time_match:
            result["time_specified"] = True
            if len(time_match.groups()) == 2:  # Start and end time
                try:
                    start_time_str = time_match.group(1)
                    end_time_str = time_match.group(2)

                    # Parse times and attach to the date we found or today's date
                    base_date = (
                        result["start_datetime"].date()
                        if result["start_datetime"]
                        else base_time.date()
                    )

                    start_time = date_parser.parse(start_time_str).time()
                    end_time = date_parser.parse(end_time_str).time()

                    start_dt = datetime.combine(base_date, start_time)
                    end_dt = datetime.combine(base_date, end_time)

                    # If end time is earlier than start time, assume it's the next day
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)

                    result["start_datetime"] = start_dt
                    result["end_datetime"] = end_dt
                    result["duration_hours"] = (
                        end_dt - start_dt
                    ).total_seconds() / 3600
                    result["duration_specified"] = True
                    break
                except:
                    pass
            elif len(time_match.groups()) == 1:  # Only start time
                try:
                    start_time_str = time_match.group(1)
                    base_date = (
                        result["start_datetime"].date()
                        if result["start_datetime"]
                        else base_time.date()
                    )

                    start_time = date_parser.parse(start_time_str).time()
                    start_dt = datetime.combine(base_date, start_time)

                    result["start_datetime"] = start_dt
                    result["end_datetime"] = start_dt + timedelta(
                        hours=default_duration_hours
                    )
                    break
                except:
                    pass

    # Check for duration patterns if we have a start time but no end time yet
    if result["start_datetime"] and not result["duration_specified"]:
        for pattern in duration_patterns:
            duration_match = re.search(pattern, text, re.IGNORECASE)
            if duration_match:
                try:
                    duration_value = int(duration_match.group(1))
                    if "hour" in pattern:
                        duration_hours = duration_value
                    else:  # minutes
                        duration_hours = duration_value / 60

                    result["duration_hours"] = duration_hours
                    result["duration_specified"] = True
                    result["end_datetime"] = result["start_datetime"] + timedelta(
                        hours=duration_hours
                    )
                    break
                except:
                    pass

    # If we have a start time but no end time, apply default duration
    if result["start_datetime"] and not result["end_datetime"]:
        result["end_datetime"] = result["start_datetime"] + timedelta(
            hours=default_duration_hours
        )

    # Check for all-day event indicators
    if re.search(r"\ball[\s-]day\b", text, re.IGNORECASE):
        result["is_all_day"] = True

        # If we have a date, adjust times to be all day
        if result["start_datetime"]:
            start_date = result["start_datetime"].date()
            result["start_datetime"] = datetime.combine(start_date, datetime.min.time())
            result["end_datetime"] = datetime.combine(start_date, datetime.max.time())

    # If we still don't have a start_datetime after all processing, use defaults
    if not result["start_datetime"]:
        # Default to tomorrow
        result["start_datetime"] = base_time + timedelta(days=1)
        result["end_datetime"] = result["start_datetime"] + timedelta(
            hours=default_duration_hours
        )

    # Ensure both datetimes have timezone info if possible
    local_tz = datetime.now().astimezone().tzinfo
    if result["start_datetime"] and result["start_datetime"].tzinfo is None:
        result["start_datetime"] = result["start_datetime"].replace(tzinfo=local_tz)
    if result["end_datetime"] and result["end_datetime"].tzinfo is None:
        result["end_datetime"] = result["end_datetime"].replace(tzinfo=local_tz)

    return result


@click.group()
def cli():
    """ORII Calendar Assistant"""
    pass


@cli.command()
@click.option(
    "--all-calendars/--primary-only",
    default=True,
    help="Include all visible calendars or just primary",
)
def chat(all_calendars):
    """Start chat mode"""
    chat_mode(all_calendars)


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


def test_llm(query: str, use_context: bool = False, debug: bool = False):
    """Test the LLM response."""
    # Get current time in a formatted string for context
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    # Parse time range from the query
    is_past, days_range, reverse_chrono = parse_time_range(query)

    # Extract search terms using more robust NLP
    search_terms = extract_search_terms(query)

    # Construct time range text based on direction and range
    if is_past:
        if days_range == 1:
            time_range_text = "Events from yesterday until now"
        elif days_range == 7:
            time_range_text = "Events from the past week until now"
        elif days_range == 14:
            time_range_text = "Events from the past two weeks until now"
        elif days_range == 30:
            time_range_text = "Events from the past month until now"
        elif days_range == 60:
            time_range_text = "Events from the past two months until now"
        elif days_range == 90:
            time_range_text = "Events from the past three months until now"
        elif days_range == 180:
            time_range_text = "Events from the past six months until now"
        elif days_range == 365:
            time_range_text = "Events from the past year until now"
        else:
            time_range_text = f"Events from {days_range} days ago until now"
    else:
        if days_range == 1:
            time_range_text = "Events from now until tomorrow"
        elif days_range == 7:
            time_range_text = "Events from now until one week in the future"
        elif days_range == 30:
            time_range_text = "Events from now until one month in the future"
        else:
            time_range_text = f"Events from now until {days_range} days in the future"

    # Fetch events with appropriate ordering
    events = get_events(is_past, days_range, search_terms, reverse_chrono)

    # Additional context for reverse chronological searches
    ordering_context = ""
    if reverse_chrono and is_past:
        ordering_context = " (showing most recent events first)"

    # Add current time context to the query
    full_query = f"Current time: {current_time}\n\n{time_range_text}{ordering_context}\n\nUser question: {query}"

    if debug:
        print(
            f"DEBUG:\nTime range: {time_range_text}\nIs past: {is_past}\nDays range: {days_range}\nReverse chrono: {reverse_chrono}\nSearch terms: {search_terms}\nEvent count: {len(events)}"
        )

    history = None
    answer = query_gpt(
        full_query, history, events, debug=debug, use_context=use_context
    )
    return answer


def extract_search_terms(query):
    """Extract meaningful search terms from user query using NLP techniques.

    Args:
        query: User query text

    Returns:
        Search terms string for use in event filtering
    """
    # If no search indicators, return None
    query_lower = query.lower()
    search_indicators = [
        "search",
        "find",
        "show",
        "about",
        "related to",
        "regarding",
        "concerning",
        "last",
        "recent",
        "latest",
        "when",
        "where",
        "what time",
    ]

    if not any(indicator in query_lower for indicator in search_indicators):
        return None

    # Define stop words to filter out
    stop_words = set(
        [
            "a",
            "an",
            "the",
            "in",
            "on",
            "at",
            "to",
            "for",
            "with",
            "about",
            "from",
            "by",
            "after",
            "before",
            "between",
            "during",
            "under",
            "over",
            "my",
            "our",
            "your",
            "when",
            "where",
            "why",
            "how",
            "what",
            "which",
            "who",
            "was",
            "is",
            "are",
            "did",
            "have",
            "had",
            "has",
            "do",
            "does",
            "last",
            "recent",
            "latest",
            "time",
            "show",
            "me",
            "tell",
            "find",
            "search",
            "get",
            "look",
            "can",
            "could",
            "would",
            "will",
            "should",
            "may",
            "might",
            "must",
            "need",
            "please",
            "thanks",
        ]
    )

    # Identify potential key entities using NLP patterns

    # Pattern 1: Look for entities after search indicators
    entity_patterns = [
        r"(?:about|regarding|concerning|on|for|related to)\s+([a-zA-Z0-9\s]+?)(?:\.|\?|$|in|on|at|with)",
        r"(?:find|search for|show)\s+(?:my|the)?\s*([a-zA-Z0-9\s]+?)(?:\.|\?|$|in|on|at|with)",
        r"(?:when|where|what time)(?:\s+\w+){0,3}\s+(?:my|the|our)?\s*([a-zA-Z0-9\s]+?)(?:\.|\?|$|in|on|at|with)",
        r"(?:last|latest|recent|previous)(?:\s+\w+){0,2}\s+([a-zA-Z0-9\s]+?)(?:\.|\?|$|in|on|at|with)",
    ]

    extracted_entities = []
    for pattern in entity_patterns:
        matches = re.finditer(pattern, query_lower)
        for match in matches:
            entity = match.group(1).strip()
            if (
                entity
                and len(entity) > 2
                and not all(word in stop_words for word in entity.split())
            ):
                extracted_entities.append(entity)

    # If we found explicit entities, use those
    if extracted_entities:
        # Get up to 3 key entities
        key_entities = extracted_entities[:3]

        # Create search terms for each entity
        search_terms = []
        for entity in key_entities:
            # Check if it's a multi-word entity
            if " " in entity and len(entity.split()) <= 3:
                search_terms.append(f'"{entity}"')  # Quote multi-word entities
            else:
                # For longer entities, use individual words
                words = [
                    w for w in entity.split() if w not in stop_words and len(w) > 2
                ]
                search_terms.extend(words)

        # Remove duplicates and join
        unique_terms = list(set(search_terms))
        if unique_terms:
            return " OR ".join(unique_terms)

    # Fallback: Process tokens and extract key terms if no explicit entities found
    tokens = query_lower.split()
    filtered_tokens = [
        token for token in tokens if token not in stop_words and len(token) > 2
    ]

    # Extract meaningful search terms (single words and up to 3-word phrases)
    if filtered_tokens:
        # For single words
        single_words = filtered_tokens[:5]  # Limit to 5 keywords

        # Add 2-word phrases if available
        two_word_phrases = []
        for i in range(len(tokens) - 1):
            phrase = f"{tokens[i]} {tokens[i+1]}"
            words = phrase.split()
            if not all(word in stop_words for word in words) and len(phrase) > 5:
                two_word_phrases.append(f'"{phrase}"')

        # Combine search terms
        all_terms = single_words + two_word_phrases[:3]  # Limit phrases

        if all_terms:
            return " OR ".join(all_terms)

    return None


# Development mode configuration
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


@cli.command()
def test():
    """Test LLM responses with real calendar data"""
    try:
        conversation_history = []

        while True:
            try:
                query = click.prompt("Test query")
                if query.lower() in ["exit", "quit", "bye"]:
                    break

                # Check for debug flag
                debug_mode = False
                if query.startswith("debug:"):
                    debug_mode = True
                    query = query[6:].strip()

                # Process the query through our updated test_llm function
                response = test_llm(query, use_context=True, debug=debug_mode)

                # Add to conversation history
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


if __name__ == "__main__":
    cli()
