"""
Intent processing functionality for the calendar assistant CLI.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from .calendar_service import get_calendar_service, get_visible_calendars
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
        elif intent_type == "list_calendars" or intent_type == "calendar_access_query":
            return process_calendar_access_query_intent()
        elif intent_type == "time_date":
            return process_time_date_intent(query, specific_date)
        elif intent_type == "greeting":
            return process_greeting_intent(query)
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
    # Force a longer time range for last/next occurrence queries
    if is_find_last_occurrence or is_find_next_occurrence:
        # Always use a full year for these queries
        days_range = 365
        logger.info(
            f"Using extended time range of {days_range} days for occurrence search"
        )

    # Calculate time range
    if specific_date:
        # When a specific date is mentioned, use only that exact date - don't use days_range
        start_time = specific_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = specific_date.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        # Set days_range to 0 to indicate exact date
        days_range = 0
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

    # Format the date for displaying in response
    date_display = ""
    if specific_date:
        date_display = specific_date.strftime("%A, %B %d, %Y")
    elif start_time and end_time:
        if (end_time - start_time).days <= 1:
            # Just one day
            date_display = start_time.strftime("%A, %B %d, %Y")
        else:
            # Date range
            date_display = (
                f"{start_time.strftime('%B %d')} to {end_time.strftime('%B %d, %Y')}"
            )

    # Call event fetching function
    from .event_retrieval import get_events_in_range

    events = get_events_in_range(
        start_time,
        end_time,
        reverse_order=reverse_chronological,
        calendar_id=specified_calendar,
    )

    # Filter events if search terms provided and no specific date/date range was identified
    # When a specific date or date range is found, we don't need to filter by search terms
    # that might include date references like "dec 8"
    filtered_events = events
    if search_terms and not (
        specific_date
        or (time_info.get("date_range_start") and time_info.get("date_range_end"))
    ):
        filtered_events = []
        for event in events:
            event_text = f"{event.get('summary', '')} {event.get('description', '')}"

            # Improve matching to support partial word matches and handle multiple search terms better
            matches = False
            event_text_lower = event_text.lower()

            # First try exact phrase matching
            if any(term.lower() in event_text_lower for term in search_terms):
                matches = True
            else:
                # If no exact match, try word-by-word partial matching
                for term in search_terms:
                    # Split terms into individual words
                    individual_words = [w for w in term.lower().split() if len(w) > 2]

                    # See if any of these individual words match
                    if individual_words and any(
                        word in event_text_lower for word in individual_words
                    ):
                        matches = True
                        logger.debug(
                            f"Partial match found for term '{term}' in event: {event.get('summary')}"
                        )
                        break

            if matches:
                filtered_events.append(event)

        search_terms_display = ", ".join(search_terms)
    else:
        # When a date is specified, don't filter by search terms
        filtered_events = events
        search_terms_display = ""

    # Format for display
    formatted_events = []
    for event in filtered_events:
        formatted_event = format_event_text(event)
        if formatted_event:  # Only add non-None events
            formatted_events.append(formatted_event)

    # Create a conversational message
    if len(formatted_events) == 0:
        if search_terms and not (
            specific_date
            or (time_info.get("date_range_start") and time_info.get("date_range_end"))
        ):
            if is_find_last_occurrence:
                message = f"I couldn't find any past events related to '{search_terms_display}' in the last {days_range} days. Nothing matching those terms appears in your calendar history."
            elif is_find_next_occurrence:
                message = f"I couldn't find any upcoming events related to '{search_terms_display}' in the next {days_range} days. Nothing matching those terms is scheduled."
            else:
                message = f"I don't see any events related to '{search_terms_display}' on {date_display}. Your schedule appears to be clear for this search."
        elif is_past:
            message = f"I couldn't find any events in your calendar for {date_display}. Either you didn't have anything scheduled or the events might not be in the system."
        else:
            message = f"You don't have any events scheduled for {date_display}. Your calendar is clear!"
    else:
        if is_find_last_occurrence:
            message = f"Found {len(formatted_events)} past events related to '{search_terms_display}' in the last {days_range} days:"
        elif is_find_next_occurrence:
            message = f"Found {len(formatted_events)} upcoming events related to '{search_terms_display}' in the next {days_range} days:"
        else:
            message = f"Here are your events for {date_display}:"

    return {
        "status": "success",
        "message": message,
        "events": formatted_events,
        "raw_events": filtered_events,  # Include raw events for further processing
        "date": date_display,
        "specific_date_query": specific_date
        is not None,  # Flag to indicate this was a specific date query
        "days_range": days_range,  # Include the days_range actually used
        "is_occurrence_query": is_find_last_occurrence or is_find_next_occurrence,
        "search_terms": (
            search_terms_display
            if search_terms
            and not (
                specific_date
                or (
                    time_info.get("date_range_start")
                    and time_info.get("date_range_end")
                )
            )
            else None
        ),
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


def process_time_date_intent(query, specific_date=None):
    """Process a time/date query intent.

    Args:
        query: The original query
        specific_date: A specific date extracted from the query

    Returns:
        Response with current date/time information
    """
    from datetime import datetime

    now = datetime.now()
    query_lower = query.lower()

    # Format based on the type of query
    if "day" in query_lower or "date" in query_lower:
        # For day/date queries
        formatted_date = now.strftime("%A, %B %d, %Y")
        return {
            "status": "success",
            "message": f"Today is {formatted_date}.",
            "date": formatted_date,
            "intent_type": "time_date",
        }
    elif "time" in query_lower:
        # For time queries
        formatted_time = now.strftime("%I:%M %p")
        return {
            "status": "success",
            "message": f"The current time is {formatted_time}.",
            "time": formatted_time,
            "intent_type": "time_date",
        }
    else:
        # Default datetime response
        formatted_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")
        return {
            "status": "success",
            "message": f"It's {formatted_datetime}.",
            "datetime": formatted_datetime,
            "intent_type": "time_date",
        }


def process_greeting_intent(query):
    """Process a greeting intent.

    Args:
        query: The original query

    Returns:
        Response with a greeting message
    """
    return {
        "status": "success",
        "message": "Hello! I'm your calendar assistant. How can I help you with your schedule today?",
        "intent_type": "greeting",
    }


def process_calendar_access_query_intent():
    """Process a calendar access query intent.

    Returns:
        Response dictionary with visible calendars
    """
    try:
        service = get_calendar_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to get calendar service",
            }

        # Get visible calendars
        visible_calendars = get_visible_calendars()

        if not visible_calendars:
            return {
                "status": "success",
                "message": "I don't have access to any visible calendars. Please make sure you have shared calendars with this application.",
                "calendars": [],
            }

        # Format calendar list for display
        calendar_list = []
        for cal in visible_calendars:
            calendar_list.append(
                {
                    "name": cal.get("summary", "Unnamed calendar"),
                    "id": cal.get("id", ""),
                    "color": cal.get("color", "#000000"),
                    "primary": cal.get("primary", False),
                }
            )

        # Create a readable list of calendar names
        calendar_names = [cal["name"] for cal in calendar_list]
        calendars_text = (
            ", ".join(calendar_names[:-1]) + " and " + calendar_names[-1]
            if len(calendar_names) > 1
            else calendar_names[0]
        )

        return {
            "status": "success",
            "message": f"I can access the following calendars: {calendars_text}",
            "calendars": calendar_list,
        }
    except Exception as e:
        logger.error(f"Error getting visible calendars: {e}")
        return {
            "status": "error",
            "message": f"Failed to retrieve calendars: {str(e)}",
        }
