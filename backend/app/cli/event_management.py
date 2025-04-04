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


def format_event_text(event: Dict[str, Any]) -> str:
    """Format an event as human-readable text.

    Args:
        event: Event dictionary (Google Calendar format)

    Returns:
        Formatted event text
    """
    # Convert Google event to our standard dictionary
    if "kind" in event and event.get("kind") == "calendar#event":
        event_dict = google_event_to_dict(event)
    else:
        # Assume it's already in our format
        event_dict = event

    # Format the event details for display
    lines = []

    # Title/summary
    lines.append(f"📅 {event_dict.get('summary', 'Untitled Event')}")

    # Date and time
    is_all_day = event_dict.get("is_all_day", False)

    if is_all_day:
        # All-day event
        start_date = event_dict.get("start_date")
        end_date = event_dict.get("end_date")

        if start_date == end_date or end_date is None:
            # Single day
            date_str = start_date.strftime("%A, %B %d, %Y")
            lines.append(f"🕒 All day on {date_str}")
        else:
            # Multiple days
            start_str = start_date.strftime("%A, %B %d, %Y")
            end_str = end_date.strftime("%A, %B %d, %Y")
            lines.append(f"🕒 All day from {start_str} to {end_str}")
    else:
        # Timed event
        start_time = event_dict.get("start_time")
        end_time = event_dict.get("end_time")

        if start_time and end_time:
            # Format start and end times
            same_day = start_time.date() == end_time.date()

            if same_day:
                # Same day
                date_str = start_time.strftime("%A, %B %d, %Y")
                start_time_str = start_time.strftime("%I:%M %p")
                end_time_str = end_time.strftime("%I:%M %p")
                lines.append(f"🕒 {date_str} from {start_time_str} to {end_time_str}")
            else:
                # Different days
                start_str = start_time.strftime("%A, %B %d, %Y at %I:%M %p")
                end_str = end_time.strftime("%A, %B %d, %Y at %I:%M %p")
                lines.append(f"🕒 From {start_str} to {end_str}")

    # Location
    if event_dict.get("location"):
        lines.append(f"📍 {event_dict['location']}")

    # Meeting link
    if event_dict.get("meeting_link"):
        lines.append(f"🔗 Meeting link: {event_dict['meeting_link']}")

    # Description (truncate if too long)
    if event_dict.get("description"):
        desc = event_dict["description"]
        if len(desc) > 200:
            desc = desc[:197] + "..."
        lines.append(f"\n{desc}")

    # Attendees
    if event_dict.get("attendees"):
        attendee_count = len(event_dict["attendees"])
        if attendee_count > 0:
            lines.append(f"\n👥 {attendee_count} attendee(s)")

            # List up to 5 attendees
            for i, attendee in enumerate(event_dict["attendees"][:5]):
                if isinstance(attendee, dict):
                    name = attendee.get("name", attendee["email"])
                    status = attendee.get("status", "")
                    status_emoji = {
                        "ACCEPTED": "✅",
                        "DECLINED": "❌",
                        "TENTATIVE": "❓",
                        "NEEDS-ACTION": "⏳",
                    }.get(status, "")

                    lines.append(f"   {status_emoji} {name}")
                else:
                    lines.append(f"   {attendee}")

            if attendee_count > 5:
                lines.append(f"   ... and {attendee_count - 5} more")

    # Recurrence
    if event_dict.get("recurrence"):
        recurrence = event_dict["recurrence"]
        # Simplify RRULE for display
        recurrence_display = recurrence.replace("RRULE:", "")
        parts = recurrence_display.split(";")
        freq = next(
            (p.replace("FREQ=", "") for p in parts if p.startswith("FREQ=")), None
        )

        if freq:
            freq_display = {
                "DAILY": "Daily",
                "WEEKLY": "Weekly",
                "MONTHLY": "Monthly",
                "YEARLY": "Yearly",
            }.get(freq, freq.title())

            lines.append(f"🔄 {freq_display} recurring event")

    # Join all lines
    return "\n".join(lines)


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
