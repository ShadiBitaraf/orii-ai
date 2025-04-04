"""
Intent processing functionality for the calendar assistant CLI.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from .calendar_service import get_calendar_service
from .event_management import (
    create_event,
    update_event,
    delete_event,
    format_event_text,
)
from .time_manager import parse_natural_language_datetime

logger = logging.getLogger(__name__)


def process_intent(
    intent_type,
    is_past,
    days_range,
    reverse_chronological,
    specific_date,
    search_terms,
    query,
    time_info,
    specified_calendar,
    is_find_last_occurrence=False,
    is_find_next_occurrence=False,
):
    """Process the detected intent and return a response.

    Args:
        intent_type: Type of intent detected
        is_past: Whether this is a query about past events
        days_range: Number of days to look ahead/back
        reverse_chronological: Whether to return events in reverse chronological order
        specific_date: Specific date to search for
        search_terms: Terms to search for
        query: Original query string
        time_info: Additional time information
        specified_calendar: Specific calendar to search
        is_find_last_occurrence: Whether to find the last occurrence
        is_find_next_occurrence: Whether to find the next occurrence

    Returns:
        Response dictionary
    """
    try:
        if intent_type == "search_events":
            return process_search_events_intent(
                is_past,
                days_range,
                reverse_chronological,
                specific_date,
                search_terms,
                query,
                time_info,
                specified_calendar,
                is_find_last_occurrence,
                is_find_next_occurrence,
            )
        elif intent_type == "create_event":
            return process_create_event_intent(query, time_info)
        elif intent_type == "update_event":
            return process_update_event_intent(query, search_terms, time_info)
        elif intent_type == "delete_event":
            return process_delete_event_intent(query, search_terms)
        elif intent_type == "get_event_details":
            return process_get_event_details_intent(query, search_terms)
        elif intent_type == "list_calendars":
            return process_list_calendars_intent()
        else:
            logger.warning(f"Unknown intent type: {intent_type}")
            return {
                "status": "error",
                "message": f"I'm not sure how to handle that request. Intent '{intent_type}' is not supported.",
            }
    except Exception as e:
        logger.error(f"Error processing intent: {e}")
        return {
            "status": "error",
            "message": f"An error occurred while processing your request: {str(e)}",
        }


def process_search_events_intent(
    is_past,
    days_range,
    reverse_chronological,
    specific_date,
    search_terms,
    query,
    time_info,
    specified_calendar,
    is_find_last_occurrence=False,
    is_find_next_occurrence=False,
):
    """Process a search events intent.

    Args:
        is_past: Whether to search past events
        days_range: Number of days to look ahead/back
        reverse_chronological: Whether to return events in reverse chronological order
        specific_date: Specific date to search for
        search_terms: Terms to search for
        query: Original query string
        time_info: Additional time information
        specified_calendar: Specific calendar to search
        is_find_last_occurrence: Whether to find the last occurrence
        is_find_next_occurrence: Whether to find the next occurrence

    Returns:
        Response dictionary with search results
    """
    # Calculate time range
    if specific_date:
        start_time = specific_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = specific_date.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    elif time_info.get("date_range_start") and time_info.get("date_range_end"):
        start_time = time_info["date_range_start"]
        end_time = time_info["date_range_end"]
    else:
        now = datetime.now()
        if is_past:
            end_time = now
            start_time = now - timedelta(days=days_range)
        else:
            start_time = now
            end_time = now + timedelta(days=days_range)

    # Call event fetching function
    from .event_retrieval import get_events_in_range

    events = get_events_in_range(
        start_time,
        end_time,
        reverse_order=reverse_chronological,
        calendar_id=specified_calendar,
    )

    # Filter events if search terms provided
    if search_terms:
        filtered_events = []
        for event in events:
            event_text = f"{event.get('summary', '')} {event.get('description', '')}"
            if any(term.lower() in event_text.lower() for term in search_terms):
                filtered_events.append(event)
        events = filtered_events

    # Format for display
    formatted_events = []
    for event in events:
        formatted_events.append(format_event_text(event))

    return {
        "status": "success",
        "message": f"Found {len(formatted_events)} events",
        "events": formatted_events,
        "raw_events": events,  # Include raw events for further processing
    }


def process_create_event_intent(query, time_info):
    """Process a create event intent.

    Args:
        query: Original query string
        time_info: Time information extracted from the query

    Returns:
        Response dictionary with created event
    """
    # Use LLM to extract event details from query
    from ..utils.llm_client import get_llm_client

    llm_client = get_llm_client()
    event_details = llm_client.extract_event_details(query, time_info)

    # Create the event
    service = get_calendar_service()
    if not service:
        return {
            "status": "error",
            "message": "Failed to get calendar service",
        }

    try:
        event = create_event(
            service,
            event_details,
            calendar_id="primary",  # Default to primary calendar
        )

        return {
            "status": "success",
            "message": "Event created successfully",
            "event": format_event_text(event),
            "raw_event": event,
        }
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return {
            "status": "error",
            "message": f"Failed to create event: {str(e)}",
        }


def process_update_event_intent(query, search_terms, time_info):
    """Process an update event intent.

    Args:
        query: Original query string
        search_terms: Terms to identify the event to update
        time_info: Time information extracted from the query

    Returns:
        Response dictionary with updated event
    """
    # TODO: Implement update event functionality
    return {
        "status": "error",
        "message": "Update event functionality not yet implemented",
    }


def process_delete_event_intent(query, search_terms):
    """Process a delete event intent.

    Args:
        query: Original query string
        search_terms: Terms to identify the event to delete

    Returns:
        Response dictionary with deletion result
    """
    # TODO: Implement delete event functionality
    return {
        "status": "error",
        "message": "Delete event functionality not yet implemented",
    }


def process_get_event_details_intent(query, search_terms):
    """Process a get event details intent.

    Args:
        query: Original query string
        search_terms: Terms to identify the event

    Returns:
        Response dictionary with event details
    """
    # TODO: Implement get event details functionality
    return {
        "status": "error",
        "message": "Get event details functionality not yet implemented",
    }


def process_list_calendars_intent():
    """Process a list calendars intent.

    Returns:
        Response dictionary with calendar list
    """
    from .query_processor import get_calendar_list_response

    return get_calendar_list_response()
