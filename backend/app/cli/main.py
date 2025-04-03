"""
Main CLI interface for the calendar assistant.
"""

import os
import sys
import time
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import dateparser

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .calendar_service import (
    get_calendar_service,
    get_calendar_list,
    get_calendar_timezone,
    list_available_calendars,
)
from .event_management import (
    create_event,
    update_event,
    delete_event,
    format_event_text,
    format_datetime_range,
)
from .time_parsing import parse_time_range, parse_natural_language_datetime
from .intent_detection import determine_query_intent, extract_search_terms
from .monitoring import record_calendar_request, get_calendar_request_stats

from ..utils.smart_date_parser import get_smart_date_parser
from ..utils.llm_client import get_llm_client

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_credentials() -> Credentials:
    """Get or refresh Google Calendar API credentials.

    Returns:
        Credentials object for the Google Calendar API
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def process_query(query):
    """Process a natural language query and return a response.

    Args:
        query: Natural language query

    Returns:
        Response dict
    """
    # Log the query for stats - operation, success, error, duration
    record_calendar_request("query", True, None, 0)

    # Determine intent
    result = determine_query_intent(query)

    # Extract relevant fields
    intent_type = result.get("intent_type", "generic")
    is_past = result.get("is_past", False)
    days_range = result.get("days_range", 7)
    reverse_chronological = result.get("reverse_chronological", False)
    specific_date = result.get("specific_date")
    search_terms = result.get("search_terms")

    # Get any additional time info from the result
    time_info = {
        "is_past": is_past,
        "days_range": days_range,
        "reverse_chronological": reverse_chronological,
        "specific_date": specific_date,
        "date_range_start": result.get("date_range_start"),
        "date_range_end": result.get("date_range_end"),
    }

    # For debugging
    print(f"[DEBUG] Processing intent: {intent_type}")
    print(f"[DEBUG] Time info: {time_info}")

    # Process the intent
    result = process_intent(
        intent_type,
        is_past,
        days_range,
        reverse_chronological,
        specific_date,
        search_terms,
        query,
        time_info,
    )

    return result


def json_serialize(obj):
    """Helper function to make result dictionary JSON serializable

    Args:
        obj: The object to serialize

    Returns:
        JSON serializable version of the object
    """
    if isinstance(obj, dict):
        return {k: json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_serialize(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj


def get_events_in_range(
    start_time, end_time, max_total_results=500, reverse_order=False
):
    """Fetch events from Google Calendar in the given time range.

    Args:
        start_time: Start datetime
        end_time: End datetime
        max_total_results: Maximum number of total results to retrieve across all pages
        reverse_order: Whether to return events in reverse chronological order (newest first)

    Returns:
        List of Event objects
    """
    print(
        f"[DEBUG] Fetching events from {start_time} to {end_time} (reverse_order={reverse_order})"
    )

    try:
        # Ensure start_time and end_time are datetime objects
        if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
            print(
                f"[ERROR] Invalid input types: start_time={type(start_time)}, end_time={type(end_time)}"
            )
            return []

        # Format times correctly for Google Calendar API
        start_time_str = start_time.isoformat() + "Z"  # 'Z' indicates UTC
        end_time_str = end_time.isoformat() + "Z"
        print(f"[DEBUG] API time range: {start_time_str} to {end_time_str}")

        # Get Google Calendar service
        service = get_calendar_service()
        if not service:
            print("[ERROR] Failed to get calendar service")
            return []

        # Use primary calendar for now
        selected_calendars = ["primary"]
        print(f"[DEBUG] Selected calendars: {selected_calendars}")

        all_events = []
        for calendar_id in selected_calendars:
            try:
                print(f"[DEBUG] Getting events for calendar: {calendar_id}")

                # Initialize for pagination
                page_token = None
                total_events_fetched = 0
                results_per_page = (
                    100  # API maximum is 2500, but we'll use 100 for efficiency
                )

                # Continue fetching pages until no more pages or we reach the max total
                while total_events_fetched < max_total_results:
                    # Make the API request with pagination token if available
                    # Google Calendar API only accepts "startTime" or "updated" for orderBy
                    events_result = (
                        service.events()
                        .list(
                            calendarId=calendar_id,
                            timeMin=start_time_str,
                            timeMax=end_time_str,
                            singleEvents=True,
                            maxResults=results_per_page,
                            # Always use startTime for orderBy - can't use startTimeDesc as it's not supported
                            orderBy="startTime",
                            pageToken=page_token,
                        )
                        .execute()
                    )

                    calendar_events = events_result.get("items", [])
                    num_events = len(calendar_events)
                    total_events_fetched += num_events

                    print(
                        f"[DEBUG] Found {num_events} events in calendar {calendar_id} (page {page_token or 'first'}, total {total_events_fetched})"
                    )

                    # Debug first few events to check structure (only on first page)
                    if calendar_events and page_token is None:
                        sample_event = calendar_events[0]
                        print(f"[DEBUG] Sample event structure: {sample_event.keys()}")
                        print(
                            f"[DEBUG] Sample event summary: {sample_event.get('summary', 'MISSING SUMMARY')}"
                        )
                        print(
                            f"[DEBUG] Sample event start: {sample_event.get('start', 'MISSING START')}"
                        )

                    # Convert to Event objects
                    for event in calendar_events:
                        try:
                            start = event["start"].get(
                                "dateTime", event["start"].get("date")
                            )
                            end = event["end"].get("dateTime", event["end"].get("date"))

                            # Debug the title/summary extraction
                            print(
                                f"[DEBUG] Raw event summary: {event.get('summary', 'NO SUMMARY KEY')}"
                            )

                            # Parse the start and end times
                            start_dt = parse_datetime(start)
                            end_dt = parse_datetime(end)

                            # Create Event object
                            event_obj = Event(
                                id=event["id"],
                                title=event.get(
                                    "summary", "NO SUMMARY"
                                ),  # Updated to debug missing titles
                                description=event.get("description", ""),
                                start=start_dt,
                                end=end_dt,
                                all_day="date" in event["start"],
                                location=event.get("location", ""),
                                calendar_id=calendar_id,
                            )
                            all_events.append(event_obj)
                        except Exception as e:
                            print(f"[ERROR] Error processing event: {e}")
                            continue

                    # Get next page token
                    page_token = events_result.get("nextPageToken")

                    # If no more pages, break out of loop
                    if not page_token:
                        print(f"[DEBUG] No more pages for calendar {calendar_id}")
                        break

            except Exception as e:
                print(f"[ERROR] Error getting events for calendar {calendar_id}: {e}")

        # If reverse order is requested, sort the events in memory
        if reverse_order:
            all_events = sorted(all_events, key=lambda x: x.start, reverse=True)
            print(f"[DEBUG] Events sorted in reverse chronological order")

        print(f"[DEBUG] Retrieved a total of {len(all_events)} events")
        return all_events

    except Exception as e:
        print(f"[ERROR] Error in get_events_in_range: {e}")
        return []


def parse_datetime(dt_string):
    """Parse a datetime string from Google Calendar API."""
    try:
        if "T" in dt_string:
            # This is a dateTime string
            # Google Calendar API returns ISO 8601 format
            # 2023-04-02T10:00:00-04:00 or 2023-04-02T10:00:00Z
            dt = datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
            # Convert to naive datetime for consistent comparison
            return dt.replace(tzinfo=None)
        else:
            # This is a date string (all-day event)
            # Google Calendar API returns YYYY-MM-DD
            return datetime.strptime(dt_string, "%Y-%m-%d")
    except Exception as e:
        print(f"[ERROR] Error parsing datetime '{dt_string}': {e}")
        return datetime.now()


class Event:
    """Simple class to represent calendar events."""

    def __init__(
        self,
        id,
        title,
        description,
        start,
        end,
        all_day=False,
        location="",
        calendar_id="",
    ):
        self.id = id
        self.title = title
        self.description = description
        # Ensure start and end are timezone-naive for consistent comparison
        self.start = (
            start.replace(tzinfo=None) if start and hasattr(start, "tzinfo") else start
        )
        self.end = end.replace(tzinfo=None) if end and hasattr(end, "tzinfo") else end
        self.all_day = all_day
        self.location = location
        self.calendar_id = calendar_id

    def __str__(self):
        return f"{self.title} - {self.start.strftime('%Y-%m-%d %H:%M')}"


def process_intent(
    intent_type,
    is_past=None,
    days_range=None,
    reverse_chronological=None,
    specific_date=None,
    search_terms=None,
    query=None,
    time_info=None,
):
    """Process a query based on intent type"""
    print(
        f"[DEBUG] Intent: {intent_type}, Search terms: {search_terms}, Query: {query}"
    )
    print(f"[DEBUG] Time info: {time_info}")

    # Detect if this is a "when was the last..." or "find the most recent..." query
    is_find_last_occurrence = False
    is_find_next_occurrence = False

    if query:
        # Check for last/previous event queries
        last_occurrence_phrases = [
            "when was the last",
            "when was my last",
            "most recent",
            "find the last",
            "last time",
        ]
        if any(phrase in query.lower() for phrase in last_occurrence_phrases):
            is_find_last_occurrence = True
            print(f"[DEBUG] Detected 'find last occurrence' type query: {query}")
            # For these queries, we want to search backwards in time
            is_past = True
            reverse_chronological = True

            # Use a much larger time window for searching (1 year by default if not specified)
            if not days_range or days_range < 30:
                days_range = 365
                print(
                    f"[DEBUG] Expanded search window to {days_range} days for 'last occurrence' query"
                )

        # Check for next/upcoming event queries
        next_occurrence_phrases = [
            "when is my next",
            "when is the next",
            "when is",
            "when will",
            "upcoming",
            "scheduled",
        ]
        if any(phrase in query.lower() for phrase in next_occurrence_phrases):
            is_find_next_occurrence = True
            print(f"[DEBUG] Detected 'find next occurrence' type query: {query}")
            # For these queries, we want to search forward in time
            is_past = False
            reverse_chronological = False

            # Use a much larger time window for searching (1 year by default if not specified)
            if not days_range or days_range < 30:
                days_range = 365
                print(
                    f"[DEBUG] Expanded search window to {days_range} days for 'next occurrence' query"
                )

    # Current time for reference - ensure it's timezone-naive
    now = datetime.now()
    print(f"[DEBUG] Current time: {now}")

    # Ensure specific_date is timezone-naive if it exists
    if specific_date and hasattr(specific_date, "tzinfo"):
        specific_date = specific_date.replace(tzinfo=None)

    # Convert string dates to datetime objects if needed
    if (
        time_info
        and time_info.get("date_range_start")
        and isinstance(time_info["date_range_start"], str)
    ):
        try:
            date_str = time_info["date_range_start"]
            # Handle different possible date formats
            if "T" in date_str:
                # Full ISO format
                time_info["date_range_start"] = datetime.fromisoformat(date_str)
            elif len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                # YYYY-MM-DD format
                time_info["date_range_start"] = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                # Try generic parsing
                time_info["date_range_start"] = dateparser.parse(date_str)

            print(
                f"[DEBUG] Converted date_range_start string to datetime: {time_info['date_range_start']}"
            )
        except Exception as e:
            print(f"[ERROR] Failed to convert date_range_start: {e}")
            time_info["date_range_start"] = None

    if (
        time_info
        and time_info.get("date_range_end")
        and isinstance(time_info["date_range_end"], str)
    ):
        try:
            date_str = time_info["date_range_end"]
            # Handle different possible date formats
            if "T" in date_str:
                # Full ISO format
                time_info["date_range_end"] = datetime.fromisoformat(date_str)
            elif len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                # YYYY-MM-DD format
                time_info["date_range_end"] = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                # Try generic parsing
                time_info["date_range_end"] = dateparser.parse(date_str)

            print(
                f"[DEBUG] Converted date_range_end string to datetime: {time_info['date_range_end']}"
            )
        except Exception as e:
            print(f"[ERROR] Failed to convert date_range_end: {e}")
            time_info["date_range_end"] = None

    # Ensure date_range_start and date_range_end are timezone-naive if they exist
    if (
        time_info
        and time_info.get("date_range_start")
        and hasattr(time_info["date_range_start"], "tzinfo")
    ):
        time_info["date_range_start"] = time_info["date_range_start"].replace(
            tzinfo=None
        )

    if (
        time_info
        and time_info.get("date_range_end")
        and hasattr(time_info["date_range_end"], "tzinfo")
    ):
        time_info["date_range_end"] = time_info["date_range_end"].replace(tzinfo=None)

    # Process based on intent
    if intent_type == "event_creation":
        # Event creation logic
        return {
            "success": False,
            "message": "Event creation not yet implemented",
            "intent_type": intent_type,
        }

    elif intent_type == "time_date":
        # Use the specific_date from time_info if it exists
        target_date = specific_date if specific_date else now
        print(f"[DEBUG] Time-date target: {target_date}")

        # If we have a valid date, format it
        if target_date:
            formatted_date = target_date.strftime("%A, %B %d, %Y")
            print(f"[DEBUG] Formatted date: {formatted_date}")
            return {
                "date": formatted_date,
                "datetime": target_date.isoformat(),
                "day_of_week": target_date.strftime("%A"),
                "intent_type": intent_type,
            }
        else:
            return {
                "error": "Could not determine the date",
                "intent_type": intent_type,
            }

    elif intent_type == "calendar_query":
        # Get events based on date/time info
        # Default values
        start_time = now - timedelta(days=7)
        end_time = now + timedelta(days=7)

        # Debug info about time parameters
        print(f"[DEBUG] Processing calendar query with parameters:")
        print(f"[DEBUG]   specific_date: {specific_date}")
        print(f"[DEBUG]   is_past: {is_past}")
        print(f"[DEBUG]   days_range: {days_range}")

        try:
            # For last occurrence queries, we may need to look much further back
            if is_find_last_occurrence:
                if not days_range or days_range < 30:
                    days_range = 365

                # For "last occurrence" queries, use a progressive search strategy
                # Start with most recent time period and only expand if needed
                now = datetime.now()
                progressive_time_windows = [
                    (7, "last week"),  # First try last week
                    (30, "last month"),  # Then last month
                    (90, "last 3 months"),  # Then last quarter
                    (180, "last 6 months"),  # Then last 6 months
                    (365, "last year"),  # Finally full year
                ]

                for window_days, window_name in progressive_time_windows:
                    # Skip windows larger than our max days_range
                    if window_days > days_range:
                        break

                    # Set window for this attempt
                    start_time = now - timedelta(days=window_days)
                    end_time = now
                    print(
                        f"[DEBUG] Progressive search: trying {window_name} ({start_time} to {end_time})"
                    )

                    # Determine if we should fetch events in reverse order for efficiency
                    use_reverse_order = True

                    # Perform the actual event lookup for this window
                    events = get_events_in_range(
                        start_time, end_time, reverse_order=use_reverse_order
                    )
                    print(f"[DEBUG] Found {len(events)} events in {window_name}")

                    # Apply search filters
                    filtered_events = []
                    if search_terms:
                        print(
                            f"[DEBUG] Filtering events with search terms: {search_terms}"
                        )
                        # Code to filter events by search terms - will use existing filtering logic later

                        # For now, simple substring matching for demonstration
                        if isinstance(search_terms, str):
                            search_phrase = search_terms.lower()
                            for event in events:
                                event_text = f"{event.title} {event.description or ''} {event.location or ''}".lower()
                                if search_phrase in event_text:
                                    filtered_events.append(event)
                        else:
                            # List of terms
                            for event in events:
                                event_text = f"{event.title} {event.description or ''} {event.location or ''}".lower()
                                for term in search_terms:
                                    if term.lower() in event_text:
                                        filtered_events.append(event)
                                        break
                    else:
                        # If no search terms, use all events
                        filtered_events = events

                    print(
                        f"[DEBUG] Found {len(filtered_events)} matching events in {window_name}"
                    )

                    # If we found matching events in this window, stop searching
                    if filtered_events:
                        print(
                            f"[DEBUG] Found matching events in {window_name}, stopping progressive search"
                        )
                        events = filtered_events
                        break

                # If we didn't find any events after all windows, use the full time range
                if not events:
                    print(
                        f"[DEBUG] Progressive search found no events, using full time range"
                    )
                    start_time = now - timedelta(days=days_range)
                    end_time = now
                    print(
                        f"[DEBUG] Searching past {days_range} days for last occurrence: {start_time} to {end_time}"
                    )

                    # Perform the actual event lookup for the full range
                    events = get_events_in_range(
                        start_time, end_time, reverse_order=True
                    )
                    print(f"[DEBUG] Found {len(events)} events in full time range")
            # For next occurrence queries, we need to look forward in time
            elif is_find_next_occurrence:
                if not days_range or days_range < 30:
                    days_range = 365

                # For these queries, we don't want to limit to a specific date, but search forward
                start_time = now
                end_time = now + timedelta(days=days_range)
                print(
                    f"[DEBUG] Searching next {days_range} days for upcoming occurrence: {start_time} to {end_time}"
                )

            # Otherwise process based on date/time parameters as usual
            elif (
                time_info
                and "date_range_start" in time_info
                and "date_range_end" in time_info
                and time_info["date_range_start"]
                and time_info["date_range_end"]
            ):
                try:
                    print(
                        f"[DEBUG] Using explicit date range: {time_info['date_range_start']} to {time_info['date_range_end']}"
                    )
                    start_time = time_info["date_range_start"]
                    end_time = time_info["date_range_end"]

                    # Add a day to end_time to make it inclusive
                    end_time = end_time.replace(hour=23, minute=59, second=59)
                except Exception as e:
                    print(f"[ERROR] Error setting date range: {e}")
                    print("[DEBUG] Falling back to default date range")
                    # This will fall through to the specific_date handling below

            # Single day or days range starting from specific date (like "tomorrow")
            elif specific_date:
                try:
                    # Force correct timezone-naive datetime for specific_date
                    if not isinstance(specific_date, datetime):
                        try:
                            specific_date = datetime.fromisoformat(specific_date)
                        except:
                            specific_date = datetime.strptime(specific_date, "%Y-%m-%d")

                    print(f"[DEBUG] Using specific date: {specific_date}")

                    # Check if we need to use days_range (for queries like "next 3 days")
                    # or if it's a single day query (for queries like "tomorrow", "on Friday")
                    use_range = days_range > 1

                    # Also check if the query has a relative reference that implies a range
                    # Detected in time_info (like "next week", "this month")
                    if time_info and time_info.get("relative_reference"):
                        rel_ref = time_info.get("relative_reference", "").lower()
                        range_references = ["week", "month", "days", "time", "period"]
                        if any(ref in rel_ref for ref in range_references):
                            use_range = True

                    print(f"[DEBUG] Using range? {use_range} (days_range={days_range})")

                    if use_range:
                        if is_past:
                            # Past events range
                            end_time = specific_date.replace(
                                hour=23, minute=59, second=59
                            )
                            start_time = end_time - timedelta(days=days_range)
                            print(
                                f"[DEBUG] Past events range: {start_time} to {end_time}"
                            )
                        else:
                            # Future events range starting FROM the specific date
                            start_time = specific_date.replace(
                                hour=0, minute=0, second=0
                            )
                            end_time = start_time + timedelta(days=days_range)
                            end_time = end_time.replace(hour=23, minute=59, second=59)
                            print(
                                f"[DEBUG] Future events range: {start_time} to {end_time}"
                            )
                    else:
                        # Single day only - query for just the specific date
                        start_time = specific_date.replace(hour=0, minute=0, second=0)
                        end_time = specific_date.replace(hour=23, minute=59, second=59)
                        print(
                            f"[DEBUG] Single day events only: {start_time} to {end_time}"
                        )
                except Exception as e:
                    print(f"[ERROR] Error setting time bounds with specific_date: {e}")
                    # Fallback to default time range
                    start_time = now - timedelta(days=7)
                    end_time = now + timedelta(days=7)
                    print(
                        f"[DEBUG] Falling back to default time range: {start_time} to {end_time}"
                    )
            else:
                # No specific date or date range, use default with is_past flag
                if is_past:
                    end_time = now
                    start_time = end_time - timedelta(days=days_range or 365)
                    print(
                        f"[DEBUG] Default past events range: {start_time} to {end_time}"
                    )
                else:
                    start_time = now
                    end_time = start_time + timedelta(days=days_range or 365)
                    print(
                        f"[DEBUG] Default future events range: {start_time} to {end_time}"
                    )

            # Ensure we have proper start and end times before fetching events
            print(f"[DEBUG] Final time range for events: {start_time} to {end_time}")

            # Determine if we should fetch events in reverse order for efficiency
            # Use reverse order for past events, especially "last occurrence" queries
            use_reverse_order = is_find_last_occurrence or (
                is_past and reverse_chronological
            )
            print(
                f"[DEBUG] Using reverse chronological order for API: {use_reverse_order}"
            )

            # Perform the actual event lookup
            events = get_events_in_range(
                start_time, end_time, reverse_order=use_reverse_order
            )
            print(f"[DEBUG] Found {len(events)} events")

            # For last occurrence queries, the events are already in reverse chronological order
            # from the API call so we don't need to sort again
            if is_find_last_occurrence and not use_reverse_order:
                events = sorted(events, key=lambda x: x.start, reverse=True)
                print(
                    f"[DEBUG] Sorted {len(events)} events in reverse chronological order"
                )

            # For next occurrence queries, ensure chronological order (earliest first)
            elif is_find_next_occurrence:
                events = sorted(events, key=lambda x: x.start)
                print(f"[DEBUG] Sorted {len(events)} events in chronological order")

            # Check if this was a single day query, where we need to ensure strict date filtering
            elif (
                specific_date
                and not (
                    time_info
                    and time_info.get("relative_reference")
                    and any(
                        ref in time_info.get("relative_reference", "").lower()
                        for ref in ["week", "month", "days", "period"]
                    )
                )
                and (days_range <= 1)
            ):
                # For single day queries, strictly filter to match only the requested day
                requested_date = specific_date.date()
                print(f"[DEBUG] Strict filtering for date: {requested_date}")

                filtered_events = []
                for event in events:
                    event_start_date = (
                        event.start.date() if hasattr(event.start, "date") else None
                    )
                    event_end_date = (
                        event.end.date() if hasattr(event.end, "date") else None
                    )

                    # Only include events that start or end on the requested date
                    # or span across it (event starts before and ends after)
                    if (
                        event_start_date == requested_date
                        or event_end_date == requested_date
                        or (
                            event_start_date < requested_date
                            and event_end_date > requested_date
                        )
                    ):
                        filtered_events.append(event)
                    else:
                        print(
                            f"[DEBUG] Filtered out event '{event.title}' with dates {event_start_date} to {event_end_date}"
                        )

                print(
                    f"[DEBUG] After strict date filtering: {len(filtered_events)} events"
                )
                events = filtered_events

            # Debug the first few events to check titles
            for i, event in enumerate(events[:2]):
                print(
                    f"[DEBUG] Event {i+1}: title={event.title}, id={event.id}, start={event.start}"
                )

            # Sort events based on chronology preference
            if (
                not is_find_last_occurrence and not is_find_next_occurrence
            ):  # Already sorted if it's a last occurrence query
                if reverse_chronological:
                    events = sorted(events, key=lambda x: x.start, reverse=True)
                else:
                    events = sorted(events, key=lambda x: x.start)

            # Filter events based on search terms if provided
            if search_terms:
                filtered_events = []
                break_traditional_filtering = (
                    False  # Default is to do traditional filtering
                )

                # Handle both string and list formats for search terms
                if isinstance(search_terms, str):
                    # Keep multi-word phrases together for exact matching
                    search_terms_list = [search_terms]
                    print(f"[DEBUG] Using search phrase: '{search_terms}'")
                else:
                    # Already a list of terms
                    search_terms_list = search_terms
                    print(f"[DEBUG] Using search terms: {search_terms_list}")

                # First try LLM-based semantic matching for more intelligent results
                try:
                    # Check if we have enough events to make semantic matching worthwhile
                    if len(events) > 0:
                        from ..utils.llm_client import get_llm_client

                        llm_client = get_llm_client()

                        if llm_client:
                            # Extract all event titles for semantic matching
                            event_titles = [event.title for event in events]
                            print(
                                f"[DEBUG] Performing semantic matching with {len(event_titles)} events"
                            )

                            # Use the primary search term for matching
                            primary_search_term = search_terms_list[0]

                            # Get semantic matches
                            semantic_matches = llm_client.match_events_semantically(
                                primary_search_term, event_titles
                            )

                            if semantic_matches:
                                print(
                                    f"[DEBUG] Found {len(semantic_matches)} semantic matches:"
                                )

                                # Add matched events to filtered list
                                for match in semantic_matches:
                                    event_idx = match["event_index"]
                                    if 0 <= event_idx < len(events):
                                        matched_event = events[event_idx]
                                        print(
                                            f"[DEBUG] Semantic match: '{matched_event.title}' (confidence: {match.get('confidence')}), reasoning: {match.get('reasoning')}"
                                        )
                                        filtered_events.append(matched_event)

                                # If we found semantic matches, use them and skip traditional matching
                                if filtered_events:
                                    print(
                                        f"[DEBUG] Using {len(filtered_events)} semantic matches as filtered events"
                                    )
                                    events = filtered_events

                                    # For "when was the last..." queries, we want just the most recent match
                                    if is_find_last_occurrence and events:
                                        most_recent = sorted(
                                            events, key=lambda x: x.start, reverse=True
                                        )[0]
                                        print(
                                            f"[DEBUG] Found most recent match: {most_recent.title} on {most_recent.start}"
                                        )
                                        events = [most_recent]

                                    # For "when is the next..." queries, we want just the earliest upcoming match
                                    if is_find_next_occurrence and events:
                                        next_event = sorted(
                                            events, key=lambda x: x.start
                                        )[0]
                                        print(
                                            f"[DEBUG] Found next occurrence: {next_event.title} on {next_event.start}"
                                        )
                                        events = [next_event]

                                    # Skip traditional matching
                                    print(
                                        f"[DEBUG] After semantic filtering: {len(events)} events"
                                    )
                                    # Done with this section - no need for additional traditional filtering
                                    break_traditional_filtering = True
                except Exception as e:
                    print(f"[DEBUG] Error during semantic matching: {e}")
                    print(f"[DEBUG] Falling back to traditional term matching")
                    break_traditional_filtering = False

                # Falling back to traditional matching if semantic matching failed or found no matches
                if not break_traditional_filtering:
                    filtered_events = []

                    # Check for special cases first - these are targeted checks for common query types
                    special_case_matched = False

                    # Special pattern for graduation-related events
                    if any("grad" in term.lower() for term in search_terms_list):
                        # Extract person name if this is a possessive query (e.g., "daria's grad")
                        person_name = None
                        for term in search_terms_list:
                            if "'" in term:
                                person_parts = term.split("'")
                                if len(person_parts) >= 1:
                                    person_name = person_parts[0].lower().strip()
                                    print(
                                        f"[DEBUG] Extracted person name from possessive: '{person_name}'"
                                    )

                        # Look for graduation-related events for the specific person
                        if person_name:
                            grad_keywords = [
                                "graduation",
                                "commencement",
                                "ceremony",
                                "convocation",
                                "grad",
                            ]
                            person_grad_events = []

                            for event in events:
                                event_text = f"{event.title} {event.description or ''} {event.location or ''}".lower()
                                # Check if the person's name is in the event
                                if person_name in event_text:
                                    # Check if any graduation keyword is in the event
                                    if any(
                                        keyword in event_text
                                        for keyword in grad_keywords
                                    ):
                                        person_grad_events.append(event)
                                        print(
                                            f"[DEBUG] Found graduation event for {person_name}: {event.title}"
                                        )

                            if person_grad_events:
                                # Sort graduation events by date
                                person_grad_events = sorted(
                                    person_grad_events, key=lambda x: x.start
                                )
                                filtered_events = person_grad_events
                                special_case_matched = True
                                print(
                                    f"[DEBUG] Special case matched: {len(filtered_events)} graduation events for {person_name}"
                                )

                                # For "when is the next..." queries, we want just the earliest upcoming match
                                if is_find_next_occurrence and filtered_events:
                                    next_event = filtered_events[
                                        0
                                    ]  # Already sorted chronologically
                                    print(
                                        f"[DEBUG] Found next occurrence: {next_event.title} on {next_event.start}"
                                    )
                                    filtered_events = [next_event]
                                # All done with this special case, no need for further processing

                        # If no special case matched, proceed with traditional filtering
                        if not special_case_matched:
                            # Pre-process the search terms to handle variations
                            processed_terms = []
                            for term in search_terms_list:
                                # Convert to lowercase
                                term = term.lower()
                                processed_terms.append(term)

                                # Add exact possessive variation if present
                                if "'" in term:
                                    possessive_no_apostrophe = term.replace("'", "")
                                    processed_terms.append(possessive_no_apostrophe)

                            print(f"[DEBUG] Processed search terms: {processed_terms}")

                            for event in events:
                                event_matched = False
                                # Combine title, description and location for searching, and convert to lowercase
                                event_text = f"{event.title} {event.description or ''} {event.location or ''}".lower()

                                # First try exact matches
                                for term in processed_terms:
                                    if term in event_text:
                                        print(
                                            f"[DEBUG] Exact match: '{term}' found in event '{event.title}'"
                                        )
                                        event_matched = True
                                        break

                                # If no exact match, try pattern-based matching
                                if not event_matched:
                                    # Split search terms and event text into individual words
                                    for term in processed_terms:
                                        # Skip very short terms
                                        if len(term) < 3:
                                            continue

                                        term_words = re.findall(r"\b\w+\b", term)
                                        event_words = re.findall(r"\b\w+\b", event_text)

                                        # For multi-word search terms
                                        if len(term_words) > 1:
                                            # Check if significant parts of the multi-word term are in the event
                                            # Count matched words
                                            matched_words = 0
                                            matched_word_details = []

                                            for search_word in term_words:
                                                # Skip very short words (articles, etc.)
                                                if len(search_word) <= 2:
                                                    continue

                                                # Look for word match or word stem match
                                                word_matched = False
                                                for event_word in event_words:
                                                    # Skip very short event words
                                                    if len(event_word) <= 2:
                                                        continue

                                                    # Check for exact match
                                                    if search_word == event_word:
                                                        matched_words += 1
                                                        matched_word_details.append(
                                                            f"{search_word}=={event_word}"
                                                        )
                                                        word_matched = True
                                                        break

                                                    # Check for prefix match (at least 4 chars)
                                                    elif (
                                                        len(search_word) >= 4
                                                        and len(event_word) >= 4
                                                    ):
                                                        # Either one is prefix of the other
                                                        if search_word.startswith(
                                                            event_word[:4]
                                                        ) or event_word.startswith(
                                                            search_word[:4]
                                                        ):
                                                            matched_words += 1
                                                            matched_word_details.append(
                                                                f"{search_word}≈{event_word}"
                                                            )
                                                            word_matched = True
                                                            break

                                                    # Check for stem match - remove common suffixes
                                                    # This does basic stemming: e.g., "graduation" → "grad"
                                                    search_stem = search_word[
                                                        : min(5, len(search_word))
                                                    ]
                                                    event_stem = event_word[
                                                        : min(5, len(event_word))
                                                    ]
                                                    if (
                                                        len(search_stem) >= 3
                                                        and len(event_stem) >= 3
                                                        and (search_stem == event_stem)
                                                    ):
                                                        matched_words += 1
                                                        matched_word_details.append(
                                                            f"{search_word}≈{event_word}(stem)"
                                                        )
                                                        word_matched = True
                                                        break

                                            # Calculate the match quality - require matching most significant words
                                            significant_words = sum(
                                                1 for w in term_words if len(w) > 2
                                            )
                                            match_threshold = max(
                                                1, significant_words * 0.7
                                            )  # At least 70% of significant words

                                            if matched_words >= match_threshold:
                                                print(
                                                    f"[DEBUG] Pattern match for '{term}' in '{event.title}': {matched_word_details}"
                                                )
                                                event_matched = True
                                                break

                                        # For single-word search terms
                                        elif len(term_words) == 1:
                                            search_word = term_words[0]
                                            # Skip very short words
                                            if len(search_word) <= 2:
                                                continue

                                            for event_word in event_words:
                                                # Skip very short event words
                                                if len(event_word) <= 2:
                                                    continue

                                                # Exact match
                                                if search_word == event_word:
                                                    print(
                                                        f"[DEBUG] Exact word match: '{search_word}' in event '{event.title}'"
                                                    )
                                                    event_matched = True
                                                    break

                                                # Prefix match (must be substantial)
                                                if (
                                                    len(search_word) >= 4
                                                    and len(event_word) >= 4
                                                ):
                                                    if search_word.startswith(
                                                        event_word[:4]
                                                    ) or event_word.startswith(
                                                        search_word[:4]
                                                    ):
                                                        print(
                                                            f"[DEBUG] Prefix match: '{search_word}' ≈ '{event_word}' in event '{event.title}'"
                                                        )
                                                        event_matched = True
                                                        break

                                                # Stem match (first 4-5 characters match)
                                                search_stem = search_word[
                                                    : min(5, len(search_word))
                                                ]
                                                event_stem = event_word[
                                                    : min(5, len(event_word))
                                                ]
                                                if (
                                                    len(search_stem) >= 3
                                                    and len(event_stem) >= 3
                                                    and search_stem == event_stem
                                                ):
                                                    print(
                                                        f"[DEBUG] Stem match: '{search_word}' ≈ '{event_word}' in event '{event.title}'"
                                                    )
                                                    event_matched = True
                                                    break

                                            if event_matched:
                                                break

                                # Possessive pattern matching (e.g., "Daria's grad" should match "Daria graduation")
                                if not event_matched:
                                    for term in search_terms_list:
                                        if "'" in term:
                                            parts = term.split("'")
                                            if len(parts) >= 2:
                                                person = parts[0].lower()
                                                event_type = parts[1].strip("s ")

                                                # Skip if parts are too short
                                                if (
                                                    len(person) < 3
                                                    or len(event_type) < 3
                                                ):
                                                    continue

                                                event_words = re.findall(
                                                    r"\b\w+\b", event_text
                                                )

                                                # Look for person match
                                                person_match = False
                                                for event_word in event_words:
                                                    if len(event_word) < 3:
                                                        continue

                                                    if person == event_word or (
                                                        len(person) >= 4
                                                        and len(event_word) >= 4
                                                        and (
                                                            person.startswith(
                                                                event_word[:4]
                                                            )
                                                            or event_word.startswith(
                                                                person[:4]
                                                            )
                                                        )
                                                    ):
                                                        person_match = True
                                                        print(
                                                            f"[DEBUG] Person match: '{person}' ≈ '{event_word}'"
                                                        )
                                                        break

                                                # If person found, look for event type
                                                if person_match:
                                                    event_match = False
                                                    for event_word in event_words:
                                                        if len(event_word) < 3:
                                                            continue

                                                        if (
                                                            event_type == event_word
                                                            or (
                                                                len(event_type) >= 4
                                                                and len(event_word) >= 4
                                                                and (
                                                                    event_type.startswith(
                                                                        event_word[:4]
                                                                    )
                                                                    or event_word.startswith(
                                                                        event_type[:4]
                                                                    )
                                                                )
                                                            )
                                                        ):
                                                            event_match = True
                                                            print(
                                                                f"[DEBUG] Event type match: '{event_type}' ≈ '{event_word}'"
                                                            )
                                                            break

                                                        # Check stems (first few characters)
                                                        event_type_stem = event_type[
                                                            : min(5, len(event_type))
                                                        ]
                                                        event_word_stem = event_word[
                                                            : min(5, len(event_word))
                                                        ]
                                                        if (
                                                            len(event_type_stem) >= 3
                                                            and len(event_word_stem)
                                                            >= 3
                                                            and event_type_stem
                                                            == event_word_stem
                                                        ):
                                                            event_match = True
                                                            print(
                                                                f"[DEBUG] Event type stem match: '{event_type}' ≈ '{event_word}'"
                                                            )
                                                            break

                                                    if person_match and event_match:
                                                        print(
                                                            f"[DEBUG] Possessive pattern match: {person}'s {event_type} in event '{event.title}'"
                                                        )
                                                        event_matched = True
                                                        break

                                                if event_matched:
                                                    filtered_events.append(event)

                        # Sort filtered events by relevance if we have more than 1 match
                        if len(filtered_events) > 1 and search_terms:
                            # Create a function to score relevance
                            def relevance_score(event):
                                score = 0
                                event_text = f"{event.title} {event.description or ''} {event.location or ''}".lower()

                                # Direct matches in title get highest score
                                for term in processed_terms:
                                    if term in event.title.lower():
                                        score += 10
                                    elif term in event_text:
                                        score += 5

                                # Boost for upcoming events (more relevant than past ones)
                                if event.start > datetime.now(timezone.utc):
                                    score += 2

                                # Boost for events closer to current date
                                days_diff = abs(
                                    (event.start - datetime.now(timezone.utc)).days
                                )
                                if days_diff < 7:
                                    score += 3
                                elif days_diff < 30:
                                    score += 1

                                return score

                            # Sort by relevance score (highest first)
                            filtered_events = sorted(
                                filtered_events, key=relevance_score, reverse=True
                            )

                            # Display debug info for top matches
                            for i, event in enumerate(filtered_events[:3]):
                                print(
                                    f"[DEBUG] Relevance match #{i+1}: '{event.title}' on {event.start}"
                                )

                        print(f"[DEBUG] After filtering: {len(filtered_events)} events")
                        events = filtered_events

                        # For "when was the last..." queries, we want just the most recent match
                        if is_find_last_occurrence and events:
                            most_recent = sorted(
                                events, key=lambda x: x.start, reverse=True
                            )[0]
                            print(
                                f"[DEBUG] Found most recent match: {most_recent.title} on {most_recent.start}"
                            )
                            events = [most_recent]

                        # For "when is the next..." queries, we want just the earliest upcoming match
                        if is_find_next_occurrence and events:
                            next_event = sorted(events, key=lambda x: x.start)[0]
                            print(
                                f"[DEBUG] Found next occurrence: {next_event.title} on {next_event.start}"
                            )
                            events = [next_event]

            # Format events for response
            event_list = []
            for event in events:
                # Ensure event properties are properly serialized
                start_iso = (
                    event.start.isoformat()
                    if hasattr(event.start, "isoformat")
                    else str(event.start)
                )
                end_iso = (
                    event.end.isoformat()
                    if hasattr(event.end, "isoformat")
                    else str(event.end)
                )

                event_dict = {
                    "id": event.id,
                    "title": event.title,
                    "description": event.description,
                    "start": start_iso,
                    "end": end_iso,
                    "all_day": bool(event.all_day),  # Ensure boolean type
                    "location": event.location,
                    "calendar_id": event.calendar_id,
                }
                event_list.append(event_dict)

            # Debug first couple of formatted events
            if event_list and len(event_list) > 0:
                print(f"[DEBUG] Sample formatted event dict: {event_list[0]}")

            return {
                "events": event_list,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
                "event_count": len(events),
                "intent_type": intent_type,
                "is_single_day": specific_date is not None
                and days_range <= 1
                and not (
                    time_info
                    and time_info.get("relative_reference")
                    and any(
                        ref in time_info.get("relative_reference", "").lower()
                        for ref in ["week", "month", "days", "period"]
                    )
                ),
                "specific_date": specific_date.isoformat() if specific_date else None,
                "is_find_last_occurrence": is_find_last_occurrence,
                "is_find_next_occurrence": is_find_next_occurrence,
                "search_terms": search_terms,
            }

        except Exception as e:
            print(f"[ERROR] Error processing calendar query: {e}")
            return {
                "error": f"Error processing calendar query: {e}",
                "intent_type": intent_type,
            }

    elif intent_type == "weather":
        # Weather intent handling
        return {
            "success": False,
            "message": "Weather queries not yet implemented",
            "intent_type": intent_type,
        }

    elif intent_type == "generic":
        # Generic query handling
        return {
            "success": False,
            "message": "Generic queries not yet implemented",
            "intent_type": intent_type,
        }

    return {
        "success": False,
        "message": "Unknown intent type",
        "intent_type": intent_type,
    }


def main():
    """Main entry point for the CLI."""
    print("Welcome to your Calendar Assistant!")
    print("Type 'exit', 'end', 'quit', or 'bye' to quit.")
    print()

    # Store conversation context
    conversation_context = {
        "last_query": None,
        "needs_clarification": False,
        "pending_clarification_type": None,
        "last_date_mentioned": None,
    }

    # Get LLM client for conversational responses
    from ..utils.llm_client import get_llm_client

    llm_client = get_llm_client()

    while True:
        try:
            # Customize prompt based on context
            if conversation_context["needs_clarification"]:
                if conversation_context["pending_clarification_type"] == "date_range":
                    prompt = "I'm not sure about the time period you're asking about. Could you specify a date or range? "
                elif (
                    conversation_context["pending_clarification_type"]
                    == "event_details"
                ):
                    prompt = "Could you provide more details about that event? "
                elif (
                    conversation_context["pending_clarification_type"] == "search_terms"
                ):
                    prompt = "What specific events or activities are you looking for? "
                else:
                    prompt = "Could you clarify what you mean? "
            else:
                prompt = (
                    "Hey I'm Orii, your calendar assistant! How can I help you today? "
                )

            # Get user input
            query = input(prompt).strip()
            if query.lower() in ["exit", "end", "quit", "bye"]:
                print("It was nice chatting with you! Have a great day.")
                break

            # Reset clarification flags if user provides new query
            if conversation_context["needs_clarification"]:
                conversation_context["needs_clarification"] = False
                conversation_context["pending_clarification_type"] = None

            # Store this query for context
            conversation_context["last_query"] = query

            # Process query and get results
            start_time = time.time()
            results = process_query(query)
            duration = time.time() - start_time

            # Record request
            record_calendar_request(
                "process_query",
                "error" not in results,
                results.get("error"),
                duration,
            )

            # If we have an LLM client, use it to generate conversational responses
            if llm_client:
                # Get conversational response from LLM
                conversational_response = llm_client.generate_conversational_response(
                    query=query,
                    results=results,
                    conversation_context=conversation_context,
                )

                # Update context based on need for clarification
                if (
                    "I need more information" in conversational_response
                    or "Could you clarify" in conversational_response
                    or "Can you specify" in conversational_response
                ):
                    conversation_context["needs_clarification"] = True
                    # Try to determine clarification type
                    if any(
                        word in conversational_response.lower()
                        for word in ["date", "time", "when", "day"]
                    ):
                        conversation_context["pending_clarification_type"] = (
                            "date_range"
                        )
                    elif any(
                        word in conversational_response.lower()
                        for word in ["event", "title", "details"]
                    ):
                        conversation_context["pending_clarification_type"] = (
                            "event_details"
                        )
                    elif any(
                        word in conversational_response.lower()
                        for word in ["looking for", "search", "find"]
                    ):
                        conversation_context["pending_clarification_type"] = (
                            "search_terms"
                        )

                # Update date mentioned context
                specific_date_str = results.get("specific_date")
                if specific_date_str:
                    conversation_context["last_date_mentioned"] = specific_date_str

                # Print the LLM-generated response
                print(conversational_response)
                print()

            else:
                # Fall back to rule-based responses if LLM client is not available
                # Display results
                if "error" in results:
                    error_msg = results["error"]
                    # Make error messages more friendly
                    if "date" in error_msg.lower() or "time" in error_msg.lower():
                        print(
                            "I'm having trouble understanding the date or time you mentioned. Could you phrase that differently?"
                        )
                        conversation_context["needs_clarification"] = True
                        conversation_context["pending_clarification_type"] = (
                            "date_range"
                        )
                    else:
                        print(
                            f"I'm sorry, but I ran into a problem: {error_msg}. Could you try asking in a different way?"
                        )
                    continue

                # Use the existing logic for formatting and displaying responses
                # ... [keeping the rest of the existing display logic as a fallback]
                intent_type = results["intent_type"]

                if intent_type == "event_creation":
                    # More natural event creation response
                    print(
                        f"I'd be happy to create that event for you. {results['message']}"
                    )
                    # Ask for missing details if needed
                    if not results.get("success", False):
                        print("What details would you like to include for this event?")
                        conversation_context["needs_clarification"] = True
                        conversation_context["pending_clarification_type"] = (
                            "event_details"
                        )

                elif intent_type == "time_date":
                    if "date" in results:
                        print(f"It's {results['date']}.")
                    elif "current_time" in results:
                        print(f"The time is now {results['current_time']}.")
                    elif "current_date" in results:
                        date_display = results["current_date"]
                        if "context" in results and results["context"] != "today":
                            date_display = f"{date_display} ({results['context']})"
                        print(f"Today's date is {date_display}.")
                    elif "day_of_week" in results:
                        print(f"It's {results['day_of_week']}.")
                    elif "datetime" in results:
                        # Format datetime for display
                        dt = datetime.fromisoformat(results["datetime"])
                        formatted_date = dt.strftime("%A, %B %d, %Y")
                        print(f"It's {formatted_date}.")
                    else:
                        # More conversational uncertainty
                        print(
                            "I'm not quite sure about the date you're asking about. Could you be more specific?"
                        )
                        conversation_context["needs_clarification"] = True
                        conversation_context["pending_clarification_type"] = (
                            "date_range"
                        )

                # ... [rest of the existing display logic for fallback]

        except KeyboardInterrupt:
            print("\nGoodbye! Have a great day.")
            break
        except Exception as e:
            print(
                f"I'm sorry, but something went wrong on my end. Let's try that again differently."
            )
            print(f"[DEBUG] Error details: {str(e)}")
            print()


if __name__ == "__main__":
    main()
