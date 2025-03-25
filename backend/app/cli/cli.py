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
from termcolor import colored
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
import sys
import pickle
import traceback
import tempfile
import urllib.parse
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union

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
    """Parse time range from query text

    Args:
        query: Natural language query string

    Returns:
        Dict with parsed time range info
    """
    # Default values
    is_past = False
    days_range = 7  # Default to a week
    reverse_chronological = False
    specific_date = None

    query_lower = query.lower()
    print(f"[DEBUG] TIME PARSING - Analyzing query for time range: '{query_lower}'")

    # Try to extract a specific date first (this takes precedence)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Various date formats to check
    date_patterns = [
        # May 18
        r"(?:on|for|at|next|this|coming|past|previous|last)\s+([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?",
        # 18th of May
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)(?:\s*,?\s*(\d{4}))?",
        # MM/DD or MM/DD/YYYY
        r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?",
        # YYYY-MM-DD format
        r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})",
    ]

    year = today.year
    for pattern in date_patterns:
        matches = re.findall(pattern, query_lower)
        if matches:
            print(f"[DEBUG] TIME PARSING - Found date pattern matches: {matches}")

            for match in matches:
                try:
                    # Handle different pattern formats
                    if len(match) == 3:  # Full patterns with possible year
                        if pattern == date_patterns[0]:  # Month name, day, [year]
                            month_str = match[0]
                            day = int(match[1])
                            year_str = match[2]
                        elif pattern == date_patterns[1]:  # Day, month name, [year]
                            day = int(match[0])
                            month_str = match[1]
                            year_str = match[2]
                        elif pattern == date_patterns[2]:  # MM/DD/[YY]
                            # For MM/DD format
                            month = int(match[0])
                            day = int(match[1])
                            year_str = match[2]
                            month_str = None
                        else:  # YYYY-MM-DD
                            year = int(match[0])
                            month = int(match[1])
                            day = int(match[2])
                            month_str = None

                        # Parse year if provided
                        if year_str and year_str.strip():
                            year = int(year_str)
                            # Handle 2-digit years
                            if year < 100:
                                year += 2000

                    # Handle month names
                    if "month_str" in locals() and month_str:
                        month_mappings = {
                            "jan": 1,
                            "january": 1,
                            "feb": 2,
                            "february": 2,
                            "mar": 3,
                            "march": 3,
                            "apr": 4,
                            "april": 4,
                            "may": 5,
                            "jun": 6,
                            "june": 6,
                            "jul": 7,
                            "july": 7,
                            "aug": 8,
                            "august": 8,
                            "sep": 9,
                            "september": 9,
                            "sept": 9,
                            "oct": 10,
                            "october": 10,
                            "nov": 11,
                            "november": 11,
                            "dec": 12,
                            "december": 12,
                        }

                        # Try to match the month name
                        matched_month = None
                        for month_name, month_num in month_mappings.items():
                            if month_str.startswith(month_name):
                                matched_month = month_num
                                break

                        if matched_month:
                            month = matched_month
                        else:
                            print(
                                f"[DEBUG] TIME PARSING - Could not parse month name: {month_str}"
                            )
                            continue

                    # Create the date object
                    try:
                        parsed_date = datetime(year, month, day)
                        if parsed_date:
                            specific_date = parsed_date
                            print(
                                f"[DEBUG] TIME PARSING - Found specific date: {specific_date}"
                            )

                            # Check if the date is in the past or future
                            is_past = specific_date < today

                            # For specific dates, we only look at events for that day
                            days_range = 1
                            break
                    except ValueError as e:
                        print(f"[DEBUG] TIME PARSING - Invalid date values: {e}")
                except Exception as e:
                    print(f"[DEBUG] TIME PARSING - Error parsing date: {e}")

    # If we found a specific date, no need to process other time indicators
    if not specific_date:
        # Other time parsing logic as before
        # Count indicators of past vs future tense
        past_indicators = len(
            [
                word
                for word in [
                    "last",
                    "previous",
                    "past",
                    "recent",
                    "ago",
                    "yesterday",
                    "earlier",
                    "before",
                    "had",
                    "was",
                    "were",
                ]
                if word in query_lower
            ]
        )

        future_indicators = len(
            [
                word
                for word in [
                    "next",
                    "upcoming",
                    "future",
                    "coming",
                    "soon",
                    "tomorrow",
                    "later",
                    "after",
                    "will",
                    "plan",
                    "schedule",
                ]
                if word in query_lower
            ]
        )

        print(
            f"[DEBUG] TIME PARSING - Past indicators: {past_indicators}, Future indicators: {future_indicators}"
        )

        # Determine if past or future based on query indicators
        if past_indicators > future_indicators:
            is_past = True

        # Extract days range for the search
        day_match = re.search(r"(\d+)\s+days?", query_lower)
        week_match = re.search(r"(\d+)\s+weeks?", query_lower)
        month_match = re.search(r"(\d+)\s+months?", query_lower)

        if day_match:
            days_range = int(day_match.group(1))
        elif week_match:
            days_range = int(week_match.group(1)) * 7
        elif month_match:
            days_range = int(month_match.group(1)) * 30
        else:
            # Look for specific time phrases
            if any(phrase in query_lower for phrase in ["today", "tonight"]):
                days_range = 1
                print(
                    "[DEBUG] TIME PARSING - Found 'today' or 'tonight', setting range to 1 day"
                )
            elif "tomorrow" in query_lower:
                days_range = 2  # Today + tomorrow
                print(
                    "[DEBUG] TIME PARSING - Found 'tomorrow', setting range to 2 days"
                )
            elif "yesterday" in query_lower:
                is_past = True
                days_range = 2  # Today + yesterday
                print(
                    "[DEBUG] TIME PARSING - Found 'yesterday', setting range to 2 days (past)"
                )
            elif "this week" in query_lower:
                days_range = 7
                print(
                    "[DEBUG] TIME PARSING - Found 'this week', setting range to 7 days"
                )
            elif "next week" in query_lower:
                days_range = 14  # Covers this week + next week
                print(
                    "[DEBUG] TIME PARSING - Found 'next week', setting range to 14 days"
                )
            elif "last week" in query_lower:
                is_past = True
                days_range = 14  # Covers this week + last week
                print(
                    "[DEBUG] TIME PARSING - Found 'last week', setting range to 14 days (past)"
                )
            elif "this month" in query_lower:
                days_range = 30
                print(
                    "[DEBUG] TIME PARSING - Found 'this month', setting range to 30 days"
                )
            else:
                print(
                    "[DEBUG] TIME PARSING - No specific temporal phrases found, using defaults"
                )

        # Special handling for queries looking for recent/last events
        if any(word in query_lower for word in ["recent", "last", "latest"]):
            reverse_chronological = True
            print(
                "[DEBUG] TIME PARSING - Found 'recent/last/latest', enabling reverse chronological order"
            )
            # For "last" queries, we should look much further back
            if is_past:
                days_range = 365  # Look back a full year for "last" queries
                print(
                    "[DEBUG] TIME PARSING - 'last' query with past context, extending days_range to 365 days"
                )

    print(
        f"[DEBUG] TIME PARSING - Final result: is_past={is_past}, days_range={days_range}, reverse_chronological={reverse_chronological}"
    )

    result = {
        "is_past": is_past,
        "days_range": days_range,
        "reverse_chronological": reverse_chronological,
    }

    # Add specific date if found
    if specific_date:
        result["specific_date"] = specific_date

    return result


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

        # Add debug information about events
        if events:
            print(f"[DEBUG] QUERY_GPT - Received {len(events)} events")
            for i, event in enumerate(events[:5]):  # Show first 5 events for debugging
                summary = event.get("summary", "Untitled")
                start_time = event.get("start_time", "Unknown")
                calendar = event.get("calendarName", "Unknown")
                print(
                    f"[DEBUG] QUERY_GPT - Event {i+1}: '{summary}' at {start_time} in {calendar}"
                )
            if len(events) > 5:
                print(f"[DEBUG] QUERY_GPT - ... and {len(events) - 5} more events")
        else:
            print("[DEBUG] QUERY_GPT - No events provided")

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
    print("[DEBUG] GET_SERVICE - Entering get_calendar_service function")

    # Check if we have a cached service that's still valid
    current_time = time.time()
    if (
        not force_refresh
        and _service_cache["service"]
        and current_time - _service_cache["timestamp"] < _service_cache["ttl"]
    ):
        # Use cached service silently
        print("[DEBUG] GET_SERVICE - Using cached service instance")
        safe_record(record_cache_operation, "hit", "calendar_service")
        return _service_cache["service"]

    try:
        # Verify environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        token_file = os.path.expanduser("~/.orii/token.json")

        print(f"[DEBUG] GET_SERVICE - Token file path: {token_file}")
        print(f"[DEBUG] GET_SERVICE - Client ID available: {bool(client_id)}")
        print(f"[DEBUG] GET_SERVICE - Client Secret available: {bool(client_secret)}")

        if not client_id or not client_secret:
            print("[ERROR] GET_SERVICE - Missing Google API credentials in environment")
            raise ValueError(
                "Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in environment variables"
            )

        creds = None
        print(f"[DEBUG] GET_SERVICE - Token file exists: {os.path.exists(token_file)}")

        # Create .orii directory if it doesn't exist
        os.makedirs(os.path.dirname(token_file), exist_ok=True)

        # Load existing credentials if available
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as token:
                    token_data = json.load(token)
                    print("[DEBUG] GET_SERVICE - Successfully loaded token file")
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                    print(f"[DEBUG] GET_SERVICE - Credentials valid: {creds.valid}")
                    print(
                        f"[DEBUG] GET_SERVICE - Credentials expired: {creds.expired if hasattr(creds, 'expired') else 'unknown'}"
                    )
                    print(
                        f"[DEBUG] GET_SERVICE - Has refresh token: {bool(creds.refresh_token) if hasattr(creds, 'refresh_token') else False}"
                    )
            except json.JSONDecodeError as e:
                print(
                    f"[ERROR] GET_SERVICE - Token file contains invalid JSON: {str(e)}"
                )
            except Exception as e:
                print(f"[ERROR] GET_SERVICE - Error loading credentials: {str(e)}")
                # If there's an error loading credentials, we'll create new ones
                pass

        # If credentials don't exist or are invalid
        if not creds or not creds.valid:
            print("[DEBUG] GET_SERVICE - Need to refresh or create new credentials")
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("[DEBUG] GET_SERVICE - Refreshing expired credentials")
                    creds.refresh(Request())
                    print("[DEBUG] GET_SERVICE - Successfully refreshed credentials")
                except Exception as e:
                    print(
                        f"[ERROR] GET_SERVICE - Failed to refresh credentials: {str(e)}"
                    )
                    creds = None

            if not creds:
                print(
                    "[DEBUG] GET_SERVICE - Need to create new credentials through OAuth flow"
                )
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
                print(
                    "[DEBUG] GET_SERVICE - Opening browser for Google authentication..."
                )
                creds = flow.run_local_server(
                    port=0, access_type="offline", include_granted_scopes="true"
                )
                print("[DEBUG] GET_SERVICE - Successfully completed OAuth flow")

            # Save the credentials
            try:
                with open(token_file, "w") as token:
                    token_json = creds.to_json()
                    token.write(token_json)
                    print(
                        "[DEBUG] GET_SERVICE - Successfully saved credentials to file"
                    )
            except Exception as e:
                print(f"[ERROR] GET_SERVICE - Failed to save credentials: {str(e)}")
                # Continue even if we can't save credentials
                pass

        # Build and return the service
        print("[DEBUG] GET_SERVICE - Building Google Calendar service")
        service = build("calendar", "v3", credentials=creds)

        # Verify service is working by making a simple API call
        try:
            # List available calendars as a test
            print(
                "[DEBUG] GET_SERVICE - Testing service with calendarList.list() API call"
            )
            calendar_list = service.calendarList().list(maxResults=10).execute()
            calendars = calendar_list.get("items", [])
            print(
                f"[DEBUG] GET_SERVICE - Service test successful, found {len(calendars)} calendars"
            )
            # Print out calendar names for debugging
            if calendars:
                calendar_names = [
                    cal.get("summary", "Unnamed") for cal in calendars[:5]
                ]
                print(
                    f"[DEBUG] GET_SERVICE - Available calendars: {', '.join(calendar_names)}"
                )
        except Exception as e:
            print(f"[ERROR] GET_SERVICE - Calendar API test request failed: {str(e)}")
            if hasattr(e, "content"):
                print(f"[ERROR] GET_SERVICE - API error details: {e.content}")

        # Cache the service
        _service_cache["service"] = service
        _service_cache["timestamp"] = current_time
        print("[DEBUG] GET_SERVICE - Service cached successfully")
        safe_record(record_cache_operation, "miss", "calendar_service")

        return service

    except Exception as e:
        print(f"[ERROR] GET_SERVICE - Error in calendar service setup: {str(e)}")
        import traceback

        print("[ERROR] GET_SERVICE - Full traceback:")
        print(traceback.format_exc())
        if isinstance(e, ValueError):
            print(
                "[ERROR] GET_SERVICE - Please check your credentials and try authenticating again"
            )
        raise


@with_calendar_cache(ttl=300)  # Cache calendar list for 5 minutes
def get_calendar_list(service):
    """Get the list of calendars with caching to reduce API calls

    Args:
        service: Google Calendar service

    Returns:
        List of calendars from the Calendar API
    """
    try:
        print("[DEBUG] GET_CALENDAR_LIST - Fetching calendar list from API")
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get("items", [])
        print(f"[DEBUG] GET_CALENDAR_LIST - Retrieved {len(calendars)} calendars")

        # Log calendar details for debugging
        if calendars:
            for i, cal in enumerate(calendars):
                print(
                    f"[DEBUG] Calendar {i+1}: ID={cal.get('id')} Name={cal.get('summary')} Selected={cal.get('selected', False)} Primary={cal.get('primary', False)}"
                )
        else:
            print("[DEBUG] GET_CALENDAR_LIST - No calendars found!")

        return calendars
    except Exception as e:
        print(f"[ERROR] GET_CALENDAR_LIST - Error fetching calendar list: {str(e)}")
        if hasattr(e, "content"):
            print(f"[ERROR] GET_CALENDAR_LIST - API error details: {e.content}")
        return []


def get_events(
    is_past,
    days_range,
    search_terms=None,
    reverse_chronological=False,
    include_all_calendars=True,
    specific_date=None,
):
    """Get events from Google Calendar within a time range

    Args:
        is_past: Whether to search in the past (vs. future)
        days_range: Number of days to search
        search_terms: Optional search terms to filter events
        reverse_chronological: Order events from newest to oldest (for "last/recent" queries)
        include_all_calendars: Whether to include all accessible calendars or just the primary
        specific_date: Optional specific date to query (overrides is_past and days_range)

    Returns:
        List of event objects
    """
    print(
        f"[DEBUG] GET_EVENTS - is_past={is_past}, days_range={days_range}, search_terms={search_terms}, "
        f"reverse_chronological={reverse_chronological}, include_all_calendars={include_all_calendars}, "
        f"specific_date={specific_date}"
    )

    # Print out search terms if present
    if search_terms:
        if isinstance(search_terms, list):
            print(
                f"[DEBUG] GET_EVENTS - Will filter events with search terms: {', '.join(search_terms)}"
            )
        else:
            print(
                f"[DEBUG] GET_EVENTS - Will filter events with search term: {search_terms}"
            )

    # Ensure days_range is an integer
    if not isinstance(days_range, int):
        try:
            days_range = int(days_range)
        except (ValueError, TypeError):
            days_range = 7

    try:
        # Get calendar service
        print("[DEBUG] GET_EVENTS - Attempting to get calendar service")
        service = get_calendar_service()
        print("[DEBUG] GET_EVENTS - Successfully got calendar service")

        # Calculate time range with RFC3339 format that Google Calendar API requires
        now = datetime.now(timezone.utc)  # Use timezone-aware datetime
        # Always format the current time
        now_formatted = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[DEBUG] GET_EVENTS - Current UTC time: {now.isoformat()}")

        # Handle specific date if provided
        if specific_date:
            print(f"[DEBUG] GET_EVENTS - Using specific date: {specific_date}")

            # Check if specific_date has a date() method (is a datetime object)
            if hasattr(specific_date, "date"):
                specific_date_date = specific_date.date()
            else:
                # If it's already a date object
                specific_date_date = specific_date

            print(
                f"[DEBUG] GET_EVENTS - Specific date converted to: {specific_date_date}"
            )

            # Create start and end of the specific date
            start_of_day = datetime.combine(specific_date_date, datetime.min.time())
            end_of_day = datetime.combine(specific_date_date, datetime.max.time())

            # Add timezone info
            start_of_day = start_of_day.replace(tzinfo=timezone.utc)
            end_of_day = end_of_day.replace(tzinfo=timezone.utc)

            # Format to RFC3339
            time_min = start_of_day.strftime("%Y-%m-%dT%H:%M:%SZ")
            time_max = end_of_day.strftime("%Y-%m-%dT%H:%M:%SZ")
            print(
                f"[DEBUG] GET_EVENTS - Specific date time range: {time_min} to {time_max}"
            )
        else:
            # Format dates in the RFC3339 format without microseconds
            if is_past:
                # Search in the past up to days_range days ago
                past_date = now - timedelta(days=days_range)
                time_min = past_date.strftime("%Y-%m-%dT%H:%M:%SZ")
                time_max = now_formatted
                print(f"[DEBUG] GET_EVENTS - Past time range: {time_min} to {time_max}")
            else:
                # Search in the future up to days_range days ahead
                future_date = now + timedelta(days=days_range)
                time_min = now_formatted
                time_max = future_date.strftime("%Y-%m-%dT%H:%M:%SZ")
                print(
                    f"[DEBUG] GET_EVENTS - Future time range: {time_min} to {time_max}"
                )

        # Log all available calendars for debugging
        all_calendars = get_calendar_list(service)
        print(f"[DEBUG] GET_EVENTS - Found {len(all_calendars)} available calendars")

        # Prepare the list of calendars to query
        calendars_to_query = []

        if include_all_calendars:
            # Get all selected calendars
            print("[DEBUG] GET_EVENTS - Including all selected calendars")
            selected_count = 0
            total_count = len(all_calendars)
            for cal in all_calendars:
                selected = cal.get("selected", False)
                cal_summary = cal.get("summary", "Unnamed Calendar")
                print(
                    f"[DEBUG] GET_EVENTS - Calendar '{cal_summary}' selected: {selected}"
                )

                if selected:
                    selected_count += 1
                    access_role = cal.get("accessRole", "unknown")
                    calendars_to_query.append(
                        {
                            "id": cal.get("id"),
                            "summary": cal_summary,
                            "primary": cal.get("primary", False),
                            "color": cal.get("backgroundColor", "#4285F4"),
                            "accessRole": access_role,
                        }
                    )
                    print(
                        f"[DEBUG] GET_EVENTS - ADDED calendar '{cal_summary}' (selected=True) with access role: {access_role}"
                    )
                else:
                    print(
                        f"[DEBUG] GET_EVENTS - SKIPPED calendar '{cal_summary}' (selected=False)"
                    )

            print(
                f"[DEBUG] GET_EVENTS - Will query {len(calendars_to_query)} selected calendars out of {total_count} total calendars"
            )
        else:
            # Just use primary calendar
            print("[DEBUG] GET_EVENTS - Including only primary calendar")
            primary_cal = next(
                (cal for cal in all_calendars if cal.get("primary", False)), None
            )
            if primary_cal:
                access_role = primary_cal.get("accessRole", "unknown")
                calendars_to_query.append(
                    {
                        "id": primary_cal.get("id", "primary"),
                        "summary": primary_cal.get("summary", "Primary Calendar"),
                        "primary": True,
                        "color": primary_cal.get("backgroundColor", "#4285F4"),
                        "accessRole": access_role,
                    }
                )
                print(
                    f"[DEBUG] GET_EVENTS - Added primary calendar with access role: {access_role}"
                )
            else:
                calendars_to_query.append(
                    {
                        "id": "primary",
                        "summary": "Primary Calendar",
                        "primary": True,
                        "color": "#4285F4",
                        "accessRole": "unknown",
                    }
                )
                print(
                    "[DEBUG] GET_EVENTS - Using default primary calendar (no primary detected in list)"
                )

        # Error if no calendars to query
        if not calendars_to_query:
            print("[ERROR] GET_EVENTS - No calendars available to query")
            return []

        # Process events from all selected calendars
        all_processed_events = []

        for calendar in calendars_to_query:
            calendar_id = calendar["id"]
            calendar_name = calendar["summary"]
            access_role = calendar.get("accessRole", "unknown")
            print(
                f"[DEBUG] GET_EVENTS - Querying calendar: {calendar_name} (ID: {calendar_id}, Access: {access_role})"
            )

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
                # For "last" queries, we want newest events first, but Google Calendar API
                # only allows "startTime" as the orderBy parameter, so we'll sort manually later
                query_params["orderBy"] = "startTime"
                print("[DEBUG] GET_EVENTS - Using reverse chronological ordering")

            print(f"[DEBUG] GET_EVENTS - API query parameters: {query_params}")

            try:
                print(
                    f"[DEBUG] GET_EVENTS - Making API call to Google Calendar for {calendar_name}"
                )
                print(
                    f"[DEBUG] GET_EVENTS - Detailed query parameters: {json.dumps(query_params, default=str)}"
                )
                events_result = service.events().list(**query_params).execute()
                raw_events = events_result.get("items", [])
                print(
                    f"[DEBUG] GET_EVENTS - Retrieved {len(raw_events)} raw events from {calendar_name}"
                )

                # If no events but we expect some, try to debug
                if not raw_events:
                    print(
                        f"[DEBUG] GET_EVENTS - No events found for {calendar_name}. Testing direct API access..."
                    )
                    # Try a simple calendar API call to see if we can access anything
                    try:
                        cal_metadata = (
                            service.calendars().get(calendarId=calendar_id).execute()
                        )
                        print(
                            f"[DEBUG] GET_EVENTS - Successfully accessed calendar metadata: {cal_metadata.get('summary')}"
                        )

                        # Try listing events without search terms/filters
                        print(
                            f"[DEBUG] GET_EVENTS - Trying to list events without filters for {calendar_name}"
                        )
                        basic_params = {
                            "calendarId": calendar_id,
                            "timeMin": time_min,
                            "timeMax": time_max,
                            "singleEvents": True,
                            "maxResults": 10,
                            "orderBy": "startTime",
                        }
                        basic_result = service.events().list(**basic_params).execute()
                        basic_events = basic_result.get("items", [])
                        print(
                            f"[DEBUG] GET_EVENTS - Without filters: found {len(basic_events)} events"
                        )

                        if basic_events:
                            # We found events without filters, so ignore search terms and use this data
                            print(
                                f"[DEBUG] GET_EVENTS - Using events without search term filter"
                            )
                            raw_events = basic_events

                    except Exception as cal_error:
                        print(
                            f"[ERROR] GET_EVENTS - Failed to access calendar metadata: {str(cal_error)}"
                        )
                        if hasattr(cal_error, "content"):
                            print(
                                f"[ERROR] GET_EVENTS - Calendar access error details: {cal_error.content}"
                            )

                # Log the first event for debugging (if any exists)
                if raw_events:
                    print(
                        f"[DEBUG] GET_EVENTS - First event preview: {raw_events[0].get('summary', 'No summary')} at {raw_events[0].get('start', {})}"
                    )

                # Process events for this calendar
                calendar_events = raw_events  # Use raw_events instead of events_result.get("items", [])
                processed_events = []

                # Apply search term filtering if needed
                if search_terms:
                    print(
                        f"[DEBUG] GET_EVENTS - Filtering {len(calendar_events)} events with search terms: {search_terms}"
                    )
                    filtered_events = []
                    for event in calendar_events:
                        event_summary = event.get("summary", "").lower()
                        event_description = event.get("description", "").lower()
                        event_location = event.get("location", "").lower()

                        # Combine all event text for searching
                        event_text = (
                            f"{event_summary} {event_description} {event_location}"
                        )

                        # Check if any search term matches the event
                        matches = False
                        matching_terms = []

                        if isinstance(search_terms, list):
                            for term in search_terms:
                                if term.lower() in event_text:
                                    matches = True
                                    matching_terms.append(term)
                        else:
                            # If search_terms is a string, check if it's in the event text
                            if search_terms.lower() in event_text:
                                matches = True
                                matching_terms = [search_terms]

                        if matches:
                            filtered_events.append(event)
                            print(
                                f"[DEBUG] GET_EVENTS - Event '{event_summary}' matched search terms: {matching_terms}"
                            )
                        else:
                            print(
                                f"[DEBUG] GET_EVENTS - Event '{event_summary}' did NOT match any search terms"
                            )

                    # Update calendar_events with the filtered list
                    print(
                        f"[DEBUG] GET_EVENTS - Filtered from {len(calendar_events)} to {len(filtered_events)} events"
                    )
                    calendar_events = filtered_events

                print(
                    f"[DEBUG] GET_EVENTS - Processing {len(calendar_events)} events for {calendar_name}"
                )
                print(f"[DEBUG] GET_EVENTS - Time range: {time_min} to {time_max}")

                for event in calendar_events:
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

                    print(
                        f"[DEBUG] GET_EVENTS - Processing event: '{summary}' with start: {start}"
                    )

                    # Handle all-day events vs. timed events
                    try:
                        if "date" in start:  # All-day event
                            start_time = start.get("date", "")
                            end_time = end.get("date", "")
                            is_all_day = True

                            # Parse timestamps for sorting - add timezone info to all-day events
                            start_dt = datetime.fromisoformat(start_time).replace(
                                tzinfo=timezone.utc
                            )
                            end_dt = datetime.fromisoformat(end_time).replace(
                                tzinfo=timezone.utc
                            )
                        else:  # Timed event
                            start_time = start.get("dateTime", "")
                            end_time = end.get("dateTime", "")
                            is_all_day = False

                            # Parse timestamps for sorting
                            start_dt = datetime.fromisoformat(
                                start_time.replace("Z", "+00:00")
                            )
                            end_dt = datetime.fromisoformat(
                                end_time.replace("Z", "+00:00")
                            )

                        # Check if this event falls within our time range
                        now = datetime.now(timezone.utc)
                        future_date = now + timedelta(days=days_range)

                        # Process this event
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
                            # Add calendar ID and name for filtering
                            "calendarId": calendar_id,
                            "calendarName": calendar_name,
                            "calendarColor": calendar.get("color"),
                            "primary": calendar.get("primary", False),
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

                        # Add debug message for each processed event
                        print(
                            f"[DEBUG] GET_EVENTS - Added event '{summary}' from {calendar_name} on {start_dt.date()}"
                        )

                    except Exception as e:
                        print(
                            f"[DEBUG] GET_EVENTS - Error processing event {summary}: {str(e)}"
                        )
                        # Try with minimal info in case of parsing error
                        try:
                            processed_event = {
                                "id": event_id,
                                "summary": summary,
                                "description": description,
                                "location": location,
                                "calendarId": calendar_id,
                                "calendarName": calendar_name,
                                "is_all_day": "date" in start,
                                "start_time": start.get(
                                    "date", start.get("dateTime", "")
                                ),
                                "end_time": end.get("date", end.get("dateTime", "")),
                                "raw_event": event,
                            }
                            processed_events.append(processed_event)
                        except:
                            # Skip this event if we can't process it at all
                            continue

                # Add this calendar's events to the main list
                all_processed_events.extend(processed_events)
                print(
                    f"[DEBUG] GET_EVENTS - Processed {len(processed_events)} events from {calendar_name}"
                )

                if specific_date:
                    print(
                        f"[DEBUG] GET_EVENTS - For specific date {specific_date.date()}, found {len(processed_events)} events"
                    )
            except Exception as api_error:
                print(
                    f"[ERROR] GET_EVENTS - API call error for {calendar_name}: {str(api_error)}"
                )
                if hasattr(api_error, "content"):
                    print(
                        f"[ERROR] GET_EVENTS - API error details: {api_error.content}"
                    )
                # Continue to next calendar rather than crashing
                continue

        # Sort all events chronologically (or reverse)
        all_processed_events.sort(
            key=lambda e: e["start_dt"], reverse=reverse_chronological
        )

        if specific_date:
            # Extra debug information for specific date queries
            date_str = (
                specific_date.date()
                if hasattr(specific_date, "date")
                else specific_date
            )
            print(
                f"[DEBUG] GET_EVENTS - After sorting, for specific date {date_str}, found {len(all_processed_events)} total events"
            )

            # Print all event summaries for debugging
            for event in all_processed_events:
                start_dt = event.get("start_dt")
                summary = event.get("summary")
                calendar_name = event.get("calendarName")
                print(
                    f"[DEBUG] GET_EVENTS - Event: '{summary}' on {start_dt} from {calendar_name}"
                )

        print(
            f"[DEBUG] GET_EVENTS - Fetched {len(all_processed_events)} total processed events from all calendars"
        )
        return all_processed_events

    except Exception as e:
        print(f"[ERROR] GET_EVENTS - Error fetching events: {str(e)}")
        import traceback

        print("[ERROR] GET_EVENTS - Full traceback:")
        print(traceback.format_exc())
        if hasattr(e, "content"):
            print(f"[ERROR] GET_EVENTS - Detailed error: {e.content}")
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
    """Format an event for text-based output.

    Args:
        event: Event dictionary with details

    Returns:
        Formatted string describing the event
    """
    summary = event.get("summary", "Untitled Event")
    calendar_name = event.get("calendarName", "Unknown Calendar")

    # Format start and end times based on whether it's an all-day event
    if event.get("is_all_day"):
        start = event.get("start_time")
        end = event.get("end_time")

        # Parse dates and format them
        try:
            start_date = datetime.fromisoformat(start)
            end_date = datetime.fromisoformat(end)
            end_date = end_date - timedelta(
                days=1
            )  # End date is exclusive in all-day events

            # Same day
            if start_date.date() == end_date.date():
                time_str = f"{start_date.strftime('%Y-%m-%d')} (All day)"
            else:
                time_str = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')} (All day)"
        except (ValueError, TypeError):
            time_str = f"{start} - {end} (All day)"
    else:
        start = event.get("start_time")
        end = event.get("end_time")

        # Parse and format datetime strings
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

            # Convert to local time for display
            local_tz = datetime.now().astimezone().tzinfo
            start_local = start_dt.astimezone(local_tz)
            end_local = end_dt.astimezone(local_tz)

            # Same day
            if start_local.date() == end_local.date():
                time_str = f"{start_local.strftime('%Y-%m-%d %I:%M %p')} - {end_local.strftime('%I:%M %p')}"
            else:
                time_str = f"{start_local.strftime('%Y-%m-%d %I:%M %p')} - {end_local.strftime('%Y-%m-%d %I:%M %p')}"
        except (ValueError, TypeError):
            time_str = f"{start} - {end}"

    # Format location if available
    location = event.get("location", "")
    location_str = f" @ {location}" if location else ""

    # Create base formatted string
    result = f"{summary}\n   {summary} at {time_str} ({calendar_name})"

    return result


def chat_mode(include_all_calendars=True):
    """Main chat interaction loop for the CLI.

    Args:
        include_all_calendars: Whether to include all visible calendars or just primary
    """
    print()
    print("Welcome to ORII, your calendar assistant.")
    print("Type 'exit' or 'quit' to end the conversation.")
    print()

    service = get_calendar_service()

    # Track conversation for context
    conversation = []

    # Main interaction loop
    while True:
        # Get user input
        prompt = colored("\nYou: ", "green")
        query = input(prompt)
        query = query.strip()

        # Check for exit command
        if query.lower() in ["exit", "quit", "bye", "goodbye"]:
            print("\nOrii: Goodbye! Have a great day.")
            break

        if not query:
            continue

        # Record the start time for performance tracking
        start_time = time.time()

        # Process the query
        try:
            # Parse time range from query (e.g., "today", "next week")
            time_range = parse_time_range(query)
            is_past = time_range["is_past"]
            days_range = time_range["days_range"]
            reverse_chronological = time_range["reverse_chronological"]
            specific_date = time_range.get("specific_date")

            # Detect intent
            intent = determine_query_intent(query)
            print(f"[DEBUG] Detected intent: {intent}")

            if intent == "LIST_EVENTS":
                # Get search terms for more specific filtering
                search_terms = extract_search_terms(query)

                # Get events based on time range and search terms - don't use search terms for initial fetch
                events = get_events(
                    is_past=is_past,
                    days_range=days_range,
                    search_terms=None,  # Don't use search terms for initial fetch
                    reverse_chronological=reverse_chronological,
                    include_all_calendars=include_all_calendars,
                    specific_date=specific_date,
                )

                if events:
                    # Format response
                    response = f"I found {len(events)} "
                    response += "upcoming " if not is_past else "recent "
                    response += "events"
                    if len(events) > 0:
                        response += f" across {len(set(e.get('calendarName') for e in events))} calendars:\n\n"

                        # Display a limited number of events (10)
                        max_display = min(10, len(events))
                        for i, event in enumerate(events[:max_display], 1):
                            response += f"{i}. {event.get('summary')}\n"
                            response += f"   {event.get('summary')} at {format_datetime_range(event.get('start_time'), event.get('end_time'), event.get('is_all_day'))} ({event.get('calendarName')})\n\n"

                        if len(events) > max_display:
                            response += (
                                f"...and {len(events) - max_display} more events.\n"
                            )
                else:
                    response = "I couldn't find any "
                    response += "upcoming " if not is_past else "past "
                    response += "events matching your criteria."

            # The issue is here: we've detected the intent is not "LIST_EVENTS" but something else
            # We're not handling the "calendar_query" intent, and we're not using a default case
            # Let's add a check for "calendar_query" intent and have a fallback for all other intents

            elif intent.get("intent_type") == "calendar_query":
                # Get events based on time range
                search_terms = extract_search_terms(query)

                # First try without search terms to get all events
                events = get_events(
                    is_past=is_past,
                    days_range=days_range,
                    search_terms=None,  # Don't use search terms for initial fetch
                    reverse_chronological=reverse_chronological,
                    include_all_calendars=include_all_calendars,
                    specific_date=specific_date,
                )

                # Pass the events and conversation to the LLM for a response
                full_query = query
                response = query_gpt(full_query, conversation, events, use_context=True)

            elif intent.get("intent_type") == "time_date":
                # Reply with current date and time
                current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
                response = f"The current time is {current_time}."

            elif intent.get("intent_type") == "greeting":
                response = (
                    "Hello! I'm your calendar assistant. How can I help you today?"
                )

            elif intent.get("intent_type") == "assistant_info":
                response = (
                    "I'm your calendar assistant. I can help you with viewing your calendar events, "
                    "creating new events, and answering questions about your schedule. Just ask me "
                    "about your upcoming events or any specific meetings you're interested in."
                )

            elif intent.get("intent_type") == "calendar_list":
                # Get calendar list
                calendars = get_calendar_list(service)
                if calendars:
                    response = f"You have access to {len(calendars)} calendars:\n\n"
                    for i, cal in enumerate(calendars, 1):
                        primary = " (Primary)" if cal.get("primary", False) else ""
                        selected = " [Selected]" if cal.get("selected", False) else ""
                        response += f"{i}. {cal.get('summary')}{primary}{selected}\n"
                else:
                    response = "I couldn't find any calendars you have access to."

            else:
                # This is our fallback case - use GPT to generate a response
                full_query = query
                response = query_gpt(full_query, conversation, use_context=False)

            # Print the response to the user
            print(f"\nOrii: {response}")

            # Update conversation history for context
            conversation.append({"role": "user", "content": query})
            conversation.append({"role": "assistant", "content": response})

            # Limit conversation history to last 10 exchanges to prevent token overflow
            if len(conversation) > 20:
                conversation = conversation[-20:]

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
        r"(?:called|titled|named|for|about)\s+([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+\.|$)",
        r"create\s+(?:an\s+)?event\s+(?:called\s+)?([a-zA-Z0-9\s]+?)(?:\s+on|\s+at|\s+\.|$)",
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


def format_datetime_range(start_time, end_time, is_all_day=False):
    """Format start and end times for an event in a readable format.

    Args:
        start_time: Start time string (ISO format)
        end_time: End time string (ISO format)
        is_all_day: Whether this is an all-day event

    Returns:
        Formatted string with the date/time range
    """
    if is_all_day:
        # Parse dates and format all-day events
        try:
            start_date = datetime.fromisoformat(start_time)
            end_date = datetime.fromisoformat(end_time)
            # End date is exclusive in all-day events, so subtract a day for display
            end_date = end_date - timedelta(days=1)

            # Same day
            if start_date.date() == end_date.date():
                return f"{start_date.strftime('%Y-%m-%d')} (All day)"
            else:
                return f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')} (All day)"
        except (ValueError, TypeError):
            return f"{start_time} - {end_time} (All day)"
    else:
        # Parse and format timed events
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            # Convert to local time for display
            local_tz = datetime.now().astimezone().tzinfo
            start_local = start_dt.astimezone(local_tz)
            end_local = end_dt.astimezone(local_tz)

            # Same day
            if start_local.date() == end_local.date():
                return f"{start_local.strftime('%Y-%m-%d %I:%M %p')} - {end_local.strftime('%I:%M %p')}"
            else:
                return f"{start_local.strftime('%Y-%m-%d %I:%M %p')} - {end_local.strftime('%Y-%m-%d %I:%M %p')}"
        except (ValueError, TypeError):
            return f"{start_time} - {end_time}"


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
    chat_mode(include_all_calendars=all_calendars)


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
    print(
        f"[DEBUG] TEST_LLM - Processing query: '{query}', use_context={use_context}, debug={debug}"
    )

    # Get current time in a formatted string for context
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    # Parse time range from the query
    is_past, days_range, reverse_chronological = parse_time_range(query)
    print(
        f"[DEBUG] TEST_LLM - Time range parsed: is_past={is_past}, days_range={days_range}, reverse_chronological={reverse_chronological}"
    )

    # Extract search terms using more robust NLP
    search_terms = extract_search_terms(query)
    print(f"[DEBUG] TEST_LLM - Search terms: {search_terms}")

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

    print(f"[DEBUG] TEST_LLM - Time range text: '{time_range_text}'")

    # Fetch events with appropriate ordering
    print(
        f"[DEBUG] TEST_LLM - About to fetch events with is_past={is_past}, days_range={days_range}, search_terms={search_terms}"
    )
    events = get_events(
        is_past, days_range, search_terms, reverse_chronological=reverse_chronological
    )
    print(f"[DEBUG] TEST_LLM - Fetched {len(events)} events")

    # Additional context for reverse chronological searches
    ordering_context = ""
    if reverse_chronological and is_past:
        ordering_context = " (showing most recent events first)"

    # Add current time context to the query
    full_query = f"Current time: {current_time}\n\n{time_range_text}{ordering_context}\n\nUser question: {query}"

    if debug:
        print(
            f"DEBUG:\nTime range: {time_range_text}\nIs past: {is_past}\nDays range: {days_range}\nReverse chronological: {reverse_chronological}\nSearch terms: {search_terms}\nEvent count: {len(events)}"
        )

    print(f"[DEBUG] TEST_LLM - Calling query_gpt with use_context={use_context}")
    history = None
    answer = query_gpt(
        full_query, history, events, debug=debug, use_context=use_context
    )
    print(f"[DEBUG] TEST_LLM - Got answer from query_gpt ({len(answer)} chars)")
    return answer


@cli.command()
@click.option(
    "--llm-test",
    is_flag=True,
    help="Test LLM connection only",
)
def test(llm_test):
    """Test chat mode with default settings"""
    print("[DEBUG] Starting test command - chat mode with default settings")
    try:
        # Check Redis connection before starting chat
        if redis_client is not None:
            try:
                redis_client.ping()
                print("[DEBUG] Redis connection is working")
            except Exception as redis_err:
                print(f"[DEBUG] Redis connection error: {str(redis_err)}")
                print("[DEBUG] Operating in no-cache mode")

        # Test LLM connection if requested
        if llm_test:
            print("[DEBUG] Testing LLM connection...")
            try:
                test_response = query_gpt(
                    "Please respond with 'LLM connection successful'",
                    None,
                    [],
                    debug=True,
                    use_context=False,
                )
                print(f"[DEBUG] LLM test response: {test_response}")
                return
            except Exception as llm_err:
                print(f"[DEBUG] LLM connection error: {str(llm_err)}")
                import traceback

                print("\n[DEBUG] LLM error traceback:")
                print(traceback.format_exc())
                return

        # Check calendar service
        try:
            service = get_calendar_service()
            print("[DEBUG] Calendar service initialized successfully")
            # Verify service with a simple API call
            try:
                calendar_list = service.calendarList().list(maxResults=1).execute()
                print("[DEBUG] Calendar API test request successful")
            except Exception as cal_api_err:
                print(f"[DEBUG] Calendar API test request failed: {str(cal_api_err)}")
        except Exception as cal_err:
            print(f"[DEBUG] Calendar service initialization error: {str(cal_err)}")

        print("[DEBUG] Starting chat mode...")
        chat_mode(include_all_calendars=True)
    except Exception as e:
        print(f"[DEBUG] Test command error: {str(e)}")
        import traceback

        print("\n[DEBUG] Full traceback:")
        print(traceback.format_exc())


def determine_query_intent(query):
    """Determine the intent of a query to properly route it"""
    print(f"[DEBUG] INTENT - Analyzing query: '{query}'")

    # Normalize query
    query_lower = query.lower()

    # Extract time range information
    time_info = parse_time_range(query)
    is_past = time_info.get("is_past", False)
    days_range = time_info.get("days_range", 7)
    reverse_chronological = time_info.get("reverse_chronological", False)
    specific_date = time_info.get("specific_date", None)

    # Special case for therapy session queries
    if "therapy" in query_lower and any(
        word in query_lower for word in ["last", "recent"]
    ):
        print(
            "[DEBUG] INTENT - Detected therapy session search, extending time range and adding search terms"
        )
        is_past = True
        days_range = 365  # Look back a full year
        reverse_chronological = True
        search_terms = ["therapy"]

    # Extract search terms (if any) to help with filtering
    if "search_terms" not in locals():
        search_terms = extract_search_terms(query)

    # Count event creation indicators
    creation_indicators = sum(
        1
        for phrase in [
            "schedule",
            "create",
            "add",
            "new",
            "make",
            "set up",
            "put on",
            "book",
        ]
        if phrase in query_lower
    )

    # Default response for calendar queries
    intent = {
        "intent_type": "calendar_query",
        "is_past": is_past,
        "days_range": days_range,
        "needs_calendar_data": True,
        "is_creation": False,
        "reverse_chronological": reverse_chronological,
    }

    # 1. Check for event creation intent
    if creation_indicators >= 1:
        intent["intent_type"] = "event_creation"
        intent["is_creation"] = True
        intent["needs_calendar_data"] = (
            False  # Don't need to fetch calendar data for creation
        )
        print("[DEBUG] INTENT - Classified as EVENT_CREATION")
        return intent

    # 2. Check for direct time/date queries
    time_date_patterns = [
        r"what (day|date|time) is (it|today)",
        r"what is the (date|time)",
        r"current (date|time)",
    ]
    if any(re.search(pattern, query_lower) for pattern in time_date_patterns):
        intent["intent_type"] = "time_date"
        intent["needs_calendar_data"] = False
        print("[DEBUG] INTENT - Classified as TIME_DATE")
        return intent

    # 3. Check for event listing intent
    list_indicators = [
        "show",
        "list",
        "get",
        "what",
        "tell me",
        "display",
        "view",
        "see",
        "find",
        "give me",
    ]
    event_plural_refs = [
        "events",
        "meetings",
        "appointments",
        "reservations",
        "schedule",
        "calendar",
        "agenda",
    ]

    # Combined time + list patterns
    time_list_patterns = [
        r"what (do|does) (i|my) (have|has)",
        r"what('s| is) (happening|going on)",
        r"what('s| is) (in|on) (my|the) (calendar|schedule)",
        r"what am i (doing|up to)",
        r"how does my (day|schedule|calendar) look",
        r"anything (happening|scheduled|planned)",
    ]

    # Count listing indicators
    list_score = sum(1 for indicator in list_indicators if indicator in query_lower)
    event_plural_score = sum(1 for ref in event_plural_refs if ref in query_lower)
    time_list_score = sum(
        1 for pattern in time_list_patterns if re.search(pattern, query_lower)
    )

    print(
        f"[DEBUG] INTENT - List indicators: {list_score}, Event plural refs: {event_plural_score}, Time list patterns: {time_list_score}"
    )

    # If we have a specific date or time phrase, and question words like "what", "how", etc., it's usually a listing
    if specific_date and list_score >= 1:
        print(
            "[DEBUG] INTENT - Classified as LIST_EVENTS due to specific date + list indicators"
        )
        intent["intent_type"] = "calendar_query"
        return intent

    # 4. Check for greetings and small talk
    greetings = [
        "hi",
        "hello",
        "hey",
        "greetings",
        "good morning",
        "good afternoon",
        "good evening",
        "howdy",
    ]
    if any(
        greeting == query_lower or greeting in query_lower.split()
        for greeting in greetings
    ):
        intent["intent_type"] = "greeting"
        intent["needs_calendar_data"] = False
        print("[DEBUG] INTENT - Classified as GREETING")
        return intent

    # 5. Check for questions about the assistant
    assistant_patterns = [
        r"who are you",
        r"what('s| is) your name",
        r"what can you do",
        r"help me",
        r"how do you work",
        r"what are you",
    ]
    if any(re.search(pattern, query_lower) for pattern in assistant_patterns):
        intent["intent_type"] = "assistant_info"
        intent["needs_calendar_data"] = False
        print("[DEBUG] INTENT - Classified as ASSISTANT_INFO")
        return intent

    # 6. Check for calendar list request
    calendar_list_patterns = [
        r"(list|show|what|which) calendars",
        r"my calendars",
        r"available calendars",
        r"what calendars do i have",
    ]
    if any(re.search(pattern, query_lower) for pattern in calendar_list_patterns):
        intent["intent_type"] = "calendar_list"
        intent["needs_calendar_data"] = False
        print("[DEBUG] INTENT - Classified as CALENDAR_LIST")
        return intent

    # 7. General calendar query (default fallback)
    # For any other query that seems calendar related
    print("[DEBUG] INTENT - Defaulting to CALENDAR_QUERY")
    intent["intent_type"] = "calendar_query"
    return intent


def extract_search_terms(query):
    """Extract search terms from a query to filter events by

    Args:
        query: Query string

    Returns:
        List of search terms
    """
    print(f"[DEBUG] EXTRACT_SEARCH - Analyzing query: '{query}'")

    # Handle empty query
    if not query:
        print("[DEBUG] EXTRACT_SEARCH - Empty query, returning None")
        return None

    # Normalize query
    query_lower = query.lower()

    # Tokenize the query
    query_tokens = re.findall(r"\b\w+\b", query_lower)
    print(f"[DEBUG] EXTRACT_SEARCH - Tokens: {query_tokens}")

    # List of words to ignore in search terms
    ignore_words = [
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "about",
        "for",
        "from",
        "in",
        "of",
        "on",
        "to",
        "with",
        "what",
        "when",
        "where",
        "who",
        "why",
        "how",
        "which",
        "calendar",
        "event",
        "events",
        "meeting",
        "meetings",
        "appointment",
        "appointments",
        "schedule",
        "scheduled",
        "show",
        "tell",
        "find",
        "search",
        "look",
        "get",
        "happening",
        "today",
        "tomorrow",
        "yesterday",
        "week",
        "month",
        "year",
        "morning",
        "afternoon",
        "evening",
        "night",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "next",
        "last",
        "this",
        "upcoming",
        "recent",
        "latest",
        "previous",
        "past",
        "future",
        "coming",
        "every",
        "all",
        "any",
        "some",
        "most",
        "few",
        "little",
        "much",
        "many",
        "more",
        "less",
        "attend",
        "attending",
        "attended",
        "go",
        "going",
        "gone",
        "went",
        "come",
        "coming",
        "came",
        "my",
        "your",
        "our",
        "their",
        "his",
        "her",
        "its",
        "their",
        "i",
        "you",
        "we",
        "they",
        "he",
        "she",
        "it",
        "me",
        "him",
        "us",
        "them",
        "am",
        "is",
        "are",
        "was",
        "were",
        "any",
        "some",
        "please",
        "thanks",
        "thank",
        "you",
        # Additional time-related words to ignore
        "time",
        "date",
        "day",
        "hour",
        "minute",
        "second",
        "o'clock",
        "pm",
        "am",
        # Question words and variants
        "what's",
        "when's",
        "where's",
        "who's",
        "how's",
        "why's",
    ]

    # Find key terms to search for
    search_terms = []
    for word in query_tokens:
        if (
            word not in ignore_words
            and len(word) > 1  # Skip single-character words
            and not word.isdigit()  # Skip pure numbers
            and not re.match(r"\d+:\d+", word)  # Skip time patterns like "3:30"
        ):
            search_terms.append(word)

    print(f"[DEBUG] EXTRACT_SEARCH - Extracted search terms: {search_terms}")

    if not search_terms:
        print("[DEBUG] EXTRACT_SEARCH - No useful search terms found, returning None")
        return None

    return search_terms


# Add this function right before "if __name__ == "__main__":"
def list_available_calendars():
    """Debug function to list all available calendars and details"""
    print("[DEBUG] Listing all available calendars...")

    try:
        service = get_calendar_service()
        calendars = get_calendar_list(service)

        if not calendars:
            print("[ERROR] No calendars found or accessible!")
            return

        print(f"Found {len(calendars)} calendars:")
        for i, cal in enumerate(calendars):
            primary = " (PRIMARY)" if cal.get("primary", False) else ""
            selected = (
                " [SELECTED]" if cal.get("selected", False) else " [NOT SELECTED]"
            )
            print(f"{i+1}. {cal.get('summary')}{primary}{selected}")
            print(f"   - ID: {cal.get('id')}")
            print(f"   - Access Role: {cal.get('accessRole', 'unknown')}")
    except Exception as e:
        print(f"[ERROR] Failed to list calendars: {str(e)}")
        if hasattr(e, "content"):
            print(f"[ERROR] API error details: {e.content}")


@cli.command()
def calendars():
    """List all available calendars for debugging"""
    list_available_calendars()


if __name__ == "__main__":
    # Set CLI mode environment variable
    os.environ["CLI_MODE"] = "true"
    # Run the CLI application
    cli()
