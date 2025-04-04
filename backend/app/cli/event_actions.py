"""
Event actions for the calendar assistant.

This module provides functions for various calendar event actions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .calendar_service import get_calendar_service

logger = logging.getLogger(__name__)


def create_event(
    event_details: Dict[str, Any], calendar_id: str = "primary"
) -> Dict[str, Any]:
    """
    Create a new event in the specified calendar.

    Args:
        event_details: Dictionary with event details (summary, start, end, etc.)
        calendar_id: ID of the calendar to create the event in

    Returns:
        The created event
    """
    logger.info(
        f"Creating event: {event_details.get('summary')} in calendar: {calendar_id}"
    )

    try:
        service = get_calendar_service()

        # Format the event object for the Google Calendar API
        event = {
            "summary": event_details.get("summary", "New Event"),
            "description": event_details.get("description", ""),
            "location": event_details.get("location", ""),
        }

        # Handle start and end times
        start_time = event_details.get("start_time")
        end_time = event_details.get("end_time")
        is_all_day = event_details.get("is_all_day", False)

        if is_all_day:
            # Format for all-day event
            if isinstance(start_time, datetime):
                start_date = start_time.date().isoformat()
            else:
                start_date = start_time

            if isinstance(end_time, datetime):
                # For all-day events, end date should be exclusive
                end_date = (end_time.date() + timedelta(days=1)).isoformat()
            else:
                end_date = end_time

            event["start"] = {"date": start_date}
            event["end"] = {"date": end_date}
        else:
            # Format for time-specific event
            if isinstance(start_time, datetime):
                start_datetime = start_time.isoformat()
            else:
                start_datetime = start_time

            if isinstance(end_time, datetime):
                end_datetime = end_time.isoformat()
            else:
                end_datetime = end_time

            event["start"] = {"dateTime": start_datetime, "timeZone": "UTC"}
            event["end"] = {"dateTime": end_datetime, "timeZone": "UTC"}

        # Add optional fields if provided
        if "attendees" in event_details:
            event["attendees"] = event_details["attendees"]

        if "reminders" in event_details:
            event["reminders"] = event_details["reminders"]

        # Create the event
        created_event = (
            service.events().insert(calendarId=calendar_id, body=event).execute()
        )
        logger.info(f"Event created: {created_event.get('htmlLink')}")

        return created_event

    except Exception as e:
        logger.error(f"Error creating event: {e}")
        raise


def update_event(
    event_id: str, event_details: Dict[str, Any], calendar_id: str = "primary"
) -> Dict[str, Any]:
    """
    Update an existing event in the specified calendar.

    Args:
        event_id: ID of the event to update
        event_details: Dictionary with updated event details
        calendar_id: ID of the calendar containing the event

    Returns:
        The updated event
    """
    logger.info(f"Updating event {event_id} in calendar {calendar_id}")

    try:
        service = get_calendar_service()

        # Get the existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Update the fields
        if "summary" in event_details:
            event["summary"] = event_details["summary"]

        if "description" in event_details:
            event["description"] = event_details["description"]

        if "location" in event_details:
            event["location"] = event_details["location"]

        # Handle start and end times
        start_time = event_details.get("start_time")
        end_time = event_details.get("end_time")
        is_all_day = event_details.get("is_all_day", False)

        if start_time:
            if is_all_day:
                if isinstance(start_time, datetime):
                    start_date = start_time.date().isoformat()
                else:
                    start_date = start_time
                event["start"] = {"date": start_date}
            else:
                if isinstance(start_time, datetime):
                    start_datetime = start_time.isoformat()
                else:
                    start_datetime = start_time
                event["start"] = {"dateTime": start_datetime, "timeZone": "UTC"}

        if end_time:
            if is_all_day:
                if isinstance(end_time, datetime):
                    # For all-day events, end date should be exclusive
                    end_date = (end_time.date() + timedelta(days=1)).isoformat()
                else:
                    end_date = end_time
                event["end"] = {"date": end_date}
            else:
                if isinstance(end_time, datetime):
                    end_datetime = end_time.isoformat()
                else:
                    end_datetime = end_time
                event["end"] = {"dateTime": end_datetime, "timeZone": "UTC"}

        # Update optional fields if provided
        if "attendees" in event_details:
            event["attendees"] = event_details["attendees"]

        if "reminders" in event_details:
            event["reminders"] = event_details["reminders"]

        # Update the event
        updated_event = (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event)
            .execute()
        )

        logger.info(f"Event updated: {updated_event.get('htmlLink')}")
        return updated_event

    except Exception as e:
        logger.error(f"Error updating event: {e}")
        raise


def delete_event(event_id: str, calendar_id: str = "primary") -> bool:
    """
    Delete an event from the specified calendar.

    Args:
        event_id: ID of the event to delete
        calendar_id: ID of the calendar containing the event

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Deleting event {event_id} from calendar {calendar_id}")

    try:
        service = get_calendar_service()

        # Delete the event
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

        logger.info(f"Event deleted successfully")
        return True

    except Exception as e:
        logger.error(f"Error deleting event: {e}")
        return False


def get_event_details(event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
    """
    Get details for a specific event.

    Args:
        event_id: ID of the event to retrieve
        calendar_id: ID of the calendar containing the event

    Returns:
        Dictionary with event details
    """
    logger.info(f"Getting details for event {event_id} from calendar {calendar_id}")

    try:
        service = get_calendar_service()

        # Get the event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        logger.info(f"Retrieved event details for {event.get('summary')}")
        return event

    except Exception as e:
        logger.error(f"Error getting event details: {e}")
        raise
