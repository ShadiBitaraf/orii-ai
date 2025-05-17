"""
Query processing functionality for the calendar assistant CLI.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.intent.intent_detection import determine_query_intent
from .monitoring import record_calendar_request
from ..core.calendar.calendar_service import get_selected_calendars, get_calendar_service
from ..core.calendar.event_management import format_event_text
from ..core.time.time_manager import parse_time_range

logger = logging.getLogger(__name__)


def process_query(query):
    """Process a natural language query and return a response.

    Args:
        query: Natural language query

    Returns:
        Response dict
    """
    # Log the query for stats - operation, success, error, duration
    record_calendar_request("query", True, None, 0)

    # Special handling for requests to just return the calendar list
    query_norm = query.lower().strip()
    if "return" in query_norm and (
        "calendar" in query_norm or "calendars" in query_norm
    ):
        logger.debug("Direct calendar list request detected")
        return get_calendar_list_response()

    # Check if this is a specific query about listing calendars
    query_lower = query.lower()

    # Direct pattern matching for calendar listing - handle many variations
    calendar_keywords = ["calendar", "calendars"]
    action_keywords = ["what", "which", "list", "show", "see", "access", "have", "tell"]

    # Check if the query is about calendars
    has_calendar_keyword = any(word in query_lower for word in calendar_keywords)
    has_action_keyword = any(word in query_lower for word in action_keywords)

    # Skip if it's clearly specifying a particular calendar to search rather than listing
    specific_calendar_indicators = ["in my", "from my", "on my", "check my"]
    is_specific_calendar_query = any(
        phrase in query_lower for phrase in specific_calendar_indicators
    )

    if has_calendar_keyword and has_action_keyword and not is_specific_calendar_query:
        logger.debug(f"Directly handling calendar listing query: {query}")
        return get_calendar_list_response()

    # Normal flow - determine intent with LLM
    result = determine_query_intent(query)

    # Extract relevant fields
    intent_type = result.get("intent_type", "generic")
    is_past = result.get("is_past", False)
    days_range = result.get("days_range", 7)
    reverse_chronological = result.get("reverse_chronological", False)
    specific_date = result.get("specific_date")
    search_terms = result.get("search_terms")
    specified_calendar = result.get("specified_calendar")
    is_find_last_occurrence = result.get("is_find_last_occurrence", False)
    is_find_next_occurrence = result.get("is_find_next_occurrence", False)

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
    logger.debug(f"Processing intent: {intent_type}")
    logger.debug(f"Time info: {time_info}")
    logger.debug(f"Specified calendar: {specified_calendar}")
    logger.debug(
        f"Finding: last={is_find_last_occurrence}, next={is_find_next_occurrence}"
    )

    # Import process_intent here to avoid circular imports
    from ..core.intent.intent_processor import process_intent

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
        specified_calendar,
        is_find_last_occurrence,
        is_find_next_occurrence,
    )

    return result


def get_calendar_list_response():
    """Get a list of available calendars.

    Returns:
        Response with calendar list information
    """
    try:
        from ..core.calendar.calendar_service import get_visible_calendars

        try:
            logger.debug("Retrieving calendar list")
            calendars = get_visible_calendars()

            if not calendars:
                return {
                    "status": "success",
                    "message": "I currently have access to your primary calendar. I don't see any additional visible calendars associated with your account. You can add more calendars or make hidden ones visible through Google Calendar if needed.",
                    "calendars": ["primary"],
                }

            calendar_list = []
            for calendar in calendars:
                try:
                    # Use 'summary' field for the calendar name
                    name = calendar.get("summary", "Unnamed Calendar")
                    calendar_id = calendar.get("id", "unknown")
                    is_primary = calendar.get("primary", False)
                    color = calendar.get("color", "#000000")
                    access_role = calendar.get("access_role", "reader")

                    # Add details to the calendar list
                    calendar_list.append(
                        {
                            "name": name,
                            "id": calendar_id,
                            "is_primary": is_primary,
                            "color": color,
                            "access_role": access_role,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error processing calendar entry: {e}")
                    # Skip this calendar and continue with others
                    continue

            calendar_names = [cal["name"] for cal in calendar_list]

            if not calendar_names:
                return {
                    "status": "success",
                    "message": "I have access to your primary calendar, but I couldn't retrieve specific details about other calendars.",
                    "calendars": ["primary"],
                }

            # Create a natural language response
            if len(calendar_names) == 1:
                message = f"I have access to 1 calendar: {calendar_names[0]}."
            else:
                names_formatted = (
                    ", ".join(calendar_names[:-1]) + " and " + calendar_names[-1]
                )
                message = f"I have access to {len(calendar_names)} visible calendars: {names_formatted}."

            return {
                "status": "success",
                "message": message,
                "calendars": calendar_list,
                "calendar_count": len(calendar_list),
            }

        except Exception as e:
            logger.error(f"Error getting visible calendars: {e}")
            # Return a more helpful error message
            return {
                "status": "success",
                "message": "I have access to your primary calendar. There might be more calendars, but I'm having trouble retrieving the full list right now.",
                "calendars": ["primary"],
            }
    except Exception as e:
        logger.error(f"Error in get_calendar_list_response: {e}")
        return {
            "status": "error",
            "message": "I encountered an issue accessing your calendars. I'll work with your primary calendar for now.",
            "calendars": ["primary"],
        }


def get_visible_calendars():
    """Helper function to get visible and selected calendars.

    Returns:
        List of formatted calendar information dictionaries.
    """
    try:
        service = get_calendar_service()
        if not service:
            logger.error("Failed to get calendar service")
            return []

        selected_calendars = get_selected_calendars(service)
        if not selected_calendars:
            logger.debug("No selected calendars found")
            return []

        # Format for display
        formatted_calendars = []
        for cal in selected_calendars:
            primary_marker = " (primary)" if cal.get("primary", False) else ""
            formatted_calendars.append(
                {
                    "name": cal.get("summary", "Unnamed") + primary_marker,
                    "id": cal.get("id", ""),
                    "color": cal.get("backgroundColor", "#000000"),
                    "is_primary": cal.get("primary", False),
                    "access_role": cal.get("accessRole", "reader"),
                    "time_zone": cal.get("timeZone", ""),
                    "selected": cal.get("selected", True),
                    "summary": cal.get("summary", "Unnamed"),
                }
            )

        logger.debug(f"Found {len(formatted_calendars)} visible calendars")
        return formatted_calendars
    except Exception as e:
        logger.error(f"Error getting visible calendars: {e}")
        return []
