"""
Event retrieval functionality for the calendar assistant CLI.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from .calendar_service import get_calendar_service

logger = logging.getLogger(__name__)


def get_events_in_range(
    start_time, end_time, max_total_results=500, reverse_order=False, calendar_id=None
):
    """Fetch events from Google Calendar in the given time range.

    Args:
        start_time: Start datetime
        end_time: End datetime
        max_total_results: Maximum number of total results to retrieve across all pages
        reverse_order: Whether to return events in reverse chronological order (newest first)
        calendar_id: Optional specific calendar ID to query. If None, query all selected and visible calendars.

    Returns:
        List of Event objects
    """
    logger.debug(
        f"Fetching events from {start_time} to {end_time} (reverse_order={reverse_order})"
    )

    try:
        # Ensure start_time and end_time are datetime objects
        if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
            logger.error(
                f"Invalid input types: start_time={type(start_time)}, end_time={type(end_time)}"
            )
            return []

        service = get_calendar_service()
        if not service:
            logger.error("Failed to get calendar service")
            return []

        # Format times as RFC3339 timestamp strings (required by Google Calendar API)
        time_min = start_time.isoformat() + "Z"  # 'Z' indicates UTC time
        time_max = end_time.isoformat() + "Z"

        # Set up query parameters
        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": min(max_total_results, 2500),  # API limit is 2500
            "singleEvents": True,  # Expand recurring events
            "orderBy": "startTime",
        }

        # If we want reverse chronological order, we'll sort the results after fetching
        # since Google Calendar API doesn't support descending order

        # Get visible calendars or use the specific calendar if provided
        if calendar_id:
            calendars_to_query = [{"id": calendar_id}]
            logger.debug(f"Querying specific calendar: {calendar_id}")
        else:
            from .calendar_service import get_selected_calendars

            calendars_to_query = get_selected_calendars(service)
            if not calendars_to_query:
                logger.debug("No calendars to query")
                return []
            logger.debug(f"Querying {len(calendars_to_query)} calendars")

        all_events = []
        for calendar in calendars_to_query:
            cal_id = calendar.get("id")
            if not cal_id:
                continue

            try:
                # Fetch events from this calendar
                events_result = (
                    service.events().list(calendarId=cal_id, **params).execute()
                )
                events = events_result.get("items", [])

                # Add calendar info to each event
                for event in events:
                    event["calendarId"] = cal_id
                    event["calendarName"] = calendar.get("name", "Unknown")

                all_events.extend(events)
                logger.debug(f"Found {len(events)} events in calendar {cal_id}")

            except Exception as e:
                logger.error(f"Error fetching events from calendar {cal_id}: {e}")
                continue

        # Sort events by start time
        all_events.sort(
            key=lambda x: x.get("start", {}).get(
                "dateTime", x.get("start", {}).get("date", "")
            ),
            reverse=reverse_order,
        )

        # Limit the total number of results
        if len(all_events) > max_total_results:
            all_events = all_events[:max_total_results]

        logger.debug(f"Returning {len(all_events)} events total")
        return all_events

    except Exception as e:
        logger.error(f"Error getting events in range: {e}")
        return []


def search_events(
    query: str,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    calendar_id: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Search for events matching a query.

    Args:
        query: Search query
        time_min: Start time
        time_max: End time
        calendar_id: Calendar ID
        max_results: Maximum number of results

    Returns:
        List of matching events
    """
    # Set default time range if not specified
    if time_min is None:
        time_min = datetime.now()
    if time_max is None:
        time_max = time_min + timedelta(days=30)

    # Get events in range
    events = get_events_in_range(
        time_min,
        time_max,
        max_total_results=max_results * 10,  # Get more to filter
        calendar_id=calendar_id,
    )

    # Filter events by query
    if query:
        filtered_events = []
        for event in events:
            event_text = (
                f"{event.get('summary', '')} {event.get('description', '')}"
            ).lower()
            if query.lower() in event_text:
                filtered_events.append(event)
        events = filtered_events

    # Limit results
    return events[:max_results]


def get_upcoming_events(
    days_ahead: int = 7, max_results: int = 10, calendar_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get upcoming events.

    Args:
        days_ahead: Number of days to look ahead
        max_results: Maximum number of results
        calendar_id: Calendar ID

    Returns:
        List of upcoming events
    """
    now = datetime.now()
    time_max = now + timedelta(days=days_ahead)
    return get_events_in_range(
        now,
        time_max,
        max_total_results=max_results,
        calendar_id=calendar_id,
    )


def get_past_events(
    days_back: int = 7, max_results: int = 10, calendar_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get past events.

    Args:
        days_back: Number of days to look back
        max_results: Maximum number of results
        calendar_id: Calendar ID

    Returns:
        List of past events
    """
    now = datetime.now()
    time_min = now - timedelta(days=days_back)
    return get_events_in_range(
        time_min,
        now,
        max_total_results=max_results,
        reverse_order=True,
        calendar_id=calendar_id,
    )
