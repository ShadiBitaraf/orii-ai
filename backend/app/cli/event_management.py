"""
Event management functions for the CLI.
"""

import time
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import logging

from .monitoring import record_calendar_request
from .calendar_service import get_calendar_timezone
from .icalendar_utils import (
    create_event_from_details,
    dict_to_google_event,
    google_event_to_dict,
    event_to_dict,
)

logger = logging.getLogger(__name__)

# Define common event type synonyms and abbreviations for better matching
EVENT_SYNONYMS = {
    "grad": ["graduation", "graduate", "commencement", "ceremony"],
    "appt": ["appointment", "meeting", "consultation"],
    "app": ["appointment", "application"],
    "doc": ["doctor", "document"],
    "dr": ["doctor", "drive"],
    "apt": ["apartment", "appointment"],
    "uni": ["university", "college"],
    "bday": ["birthday", "celebration"],
    "anniv": ["anniversary", "celebration"],
    "conf": ["conference", "meeting", "call"],
    "mtg": ["meeting", "call"],
    "vac": ["vacation", "holiday", "trip"],
    "laser": ["treatment", "appointment", "procedure", "therapy", "session"],
}


def get_expanded_search_terms(search_term):
    """
    Expand a search term to include synonyms and abbreviations.

    Args:
        search_term: Original search term

    Returns:
        List of expanded search terms including the original
    """
    expanded_terms = [search_term]
    search_words = re.findall(r"\b\w+\b", search_term.lower())

    for word in search_words:
        if word in EVENT_SYNONYMS:
            for synonym in EVENT_SYNONYMS[word]:
                # Replace the word with its synonym
                expanded_term = search_term.lower().replace(word, synonym)
                expanded_terms.append(expanded_term)

    return expanded_terms


def create_event(service, event_details, calendar_id="primary"):
    """Create calendar event with comprehensive details using iCalendar

    Args:
        service: Google Calendar service
        event_details: Dictionary with event details
        calendar_id: Calendar ID to create event in (default: primary)

    Returns:
        Created event dictionary
    """
    start_time_perf = time.time()
    try:
        # Get user's timezone setting from the calendar
        user_timezone = get_calendar_timezone(service, calendar_id)

        # Add timezone to event details if not already set
        if user_timezone and not event_details.get("timezone"):
            event_details["timezone"] = user_timezone

        # First, convert our event details to standard iCalendar format
        # This will handle all the complex logic for dates, times, recurrence, etc.

        # Convert our dict to Google Calendar format
        google_event_dict = dict_to_google_event(event_details)

        # Create the event in Google Calendar
        result = (
            service.events()
            .insert(
                calendarId=calendar_id,
                body=google_event_dict,
                conferenceDataVersion=(
                    1
                    if (
                        event_details.get("add_meet", False)
                        or event_details.get("meeting_link")
                    )
                    else 0
                ),
            )
            .execute()
        )

        # Convert Google result back to our dictionary format
        created_event = google_event_to_dict(result)

        # Record performance and success
        duration = time.time() - start_time_perf
        record_calendar_request("create_event", True, None, duration)

        return created_event
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("create_event", False, str(e), duration)
        logger.error(f"Error creating event: {e}")
        raise


def update_event(service, event_id, updates, calendar_id="primary"):
    """Update an existing calendar event

    Args:
        service: Google Calendar service
        event_id: ID of the event to update
        updates: Dictionary with updated event details
        calendar_id: Calendar ID (default: primary)

    Returns:
        Updated event dictionary
    """
    start_time_perf = time.time()
    try:
        # Get the existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Convert to our standard dictionary format
        event_dict = google_event_to_dict(event)

        # Apply updates
        for key, value in updates.items():
            if value is not None:  # Only update if value is provided
                event_dict[key] = value

        # Convert updated dict to Google Calendar format
        google_event_dict = dict_to_google_event(event_dict)

        # Update the event
        result = (
            service.events()
            .update(
                calendarId=calendar_id,
                eventId=event_id,
                body=google_event_dict,
                conferenceDataVersion=(
                    1
                    if (
                        event_dict.get("add_meet", False)
                        or event_dict.get("meeting_link")
                    )
                    else 0
                ),
            )
            .execute()
        )

        # Record performance and success
        duration = time.time() - start_time_perf
        record_calendar_request("update_event", True, None, duration)

        # Convert result back to our dictionary format
        return google_event_to_dict(result)
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("update_event", False, str(e), duration)
        logger.error(f"Error updating event: {e}")
        raise


def delete_event(service, event_id, calendar_id="primary"):
    """Delete a calendar event

    Args:
        service: Google Calendar service
        event_id: ID of the event to delete
        calendar_id: Calendar ID (default: primary)

    Returns:
        True if deleted successfully, False otherwise
    """
    start_time_perf = time.time()
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

        # Record performance and success
        duration = time.time() - start_time_perf
        record_calendar_request("delete_event", True, None, duration)

        return True
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("delete_event", False, str(e), duration)
        logger.error(f"Error deleting event: {e}")
        return False


def format_event_text(event):
    """Format an event for text display.

    Args:
        event: Event dictionary

    Returns:
        Formatted event string
    """
    # Skip events with empty titles (likely artifacts or hidden events)
    if not event.get("summary") and not event.get("title"):
        return None

    # Handle Google Calendar API format
    if "summary" in event:
        title = event.get("summary", "Untitled Event")

        # Skip events with title "Untitled Event"
        if title == "Untitled Event":
            return None

        # Get start/end times
        start = event.get("start", {})
        end = event.get("end", {})

        # Format date/time
        start_time = ""
        end_time = ""

        if "dateTime" in start:
            start_dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
            start_time = start_dt.strftime("%I:%M %p")
        elif "date" in start:
            start_time = "all day"

        if "dateTime" in end:
            end_dt = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))
            end_time = end_dt.strftime("%I:%M %p")

        location = event.get("location", "")

        # Include calendar name if available
        calendar_info = ""
        if "calendarName" in event:
            calendar_info = f" on {event['calendarName']}"

        # Format based on whether it's an all-day event
        if start_time == "all day":
            return f"{title} all day{calendar_info}"
        else:
            if end_time:
                time_range = f"{start_time} to {end_time}"
            else:
                time_range = start_time

            if location:
                return f"{time_range}: {title} at {location}{calendar_info}"
            else:
                return f"{time_range}: {title}{calendar_info}"

    # Handle custom format
    elif "title" in event:
        title = event.get("title", "")
        start = event.get("start", "")
        end = event.get("end", "")
        location = event.get("location", "")

        # Include calendar name if available
        calendar_info = ""
        if "calendar_name" in event:
            calendar_info = f" on {event['calendar_name']}"

        if start and end:
            if location:
                return f"{start} to {end}: {title} at {location}{calendar_info}"
            else:
                return f"{start} to {end}: {title}{calendar_info}"
        else:
            return title

    # Fallback format
    return str(event)


def format_datetime_range(start_time, end_time, is_all_day=False):
    """
    Format a datetime range for display.

    This is a simplified wrapper for backward compatibility.

    Args:
        start_time: Start datetime (string or datetime object)
        end_time: End datetime (string or datetime object)
        is_all_day: Whether this is an all-day event

    Returns:
        Formatted datetime range string
    """
    from .time_manager import format_datetime_range as tm_format_datetime_range

    return tm_format_datetime_range(start_time, end_time, is_all_day)
