"""
Intent processing functionality for the calendar assistant CLI.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import re

from ..calendar.calendar_service import get_calendar_service, get_visible_calendars
from ..calendar.event_management import (
    create_event,
    update_event,
    delete_event,
    format_event_text,
)
from ..time.time_manager import parse_natural_language_datetime, parse_time_range

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
    from ..calendar.event_retrieval import get_events_in_range
    from datetime import datetime, timedelta

    logger.debug(f"Processing search events intent")
    logger.debug(f"Search terms: {search_terms}")
    logger.debug(f"Days range: {days_range}")
    logger.debug(f"Is past: {is_past}")
    logger.debug(f"Specific date: {specific_date}")

    # Check if this is a contextual follow-up asking for meeting details
    is_meeting_detail_query = (
        search_terms
        and any(
            word in query.lower()
            for word in ["zoom", "link", "location", "details", "info", "information"]
        )
        and any(
            word in " ".join(search_terms).lower()
            for word in ["meeting", "call", "session"]
        )
    )

    if is_meeting_detail_query:
        # For meeting detail queries, search more broadly but focus on recent events
        logger.debug("Detected meeting detail query - expanding search range")
        days_range = min(days_range * 2, 30)  # Look a bit wider but cap at 30 days

    # Determine the time range for search
    now = datetime.now()
    if specific_date:
        # Use the specific date boundaries
        start_time = specific_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = specific_date.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    elif time_info.get("date_range_start") and time_info.get("date_range_end"):
        # Use explicit date range
        start_time = time_info["date_range_start"]
        end_time = time_info["date_range_end"]
    else:
        # Use days_range
        if is_past:
            end_time = now
            start_time = now - timedelta(days=days_range)
        else:
            start_time = now
            end_time = now + timedelta(days=days_range)

    logger.debug(f"Searching events from {start_time} to {end_time}")

    # Get events from calendar
    events = get_events_in_range(start_time, end_time)
    logger.debug(f"Found {len(events)} total events in range")

    # ADDITIONAL FILTERING: When a specific date is requested, ensure events actually start on that date
    if specific_date:
        filtered_events = []
        target_date = specific_date.date()

        for event in events:
            event_start = event.get("start", {})

            # Get the event start date
            if "dateTime" in event_start:
                # Event has specific time
                try:
                    event_dt = datetime.fromisoformat(
                        event_start["dateTime"].replace("Z", "")
                    )
                    event_date = event_dt.date()
                except Exception:
                    continue
            elif "date" in event_start:
                # All-day event
                try:
                    event_date = datetime.fromisoformat(event_start["date"]).date()
                except Exception:
                    continue
            else:
                continue

            # Only include events that start on the requested date
            if event_date == target_date:
                filtered_events.append(event)

        events = filtered_events
        logger.debug(
            f"Filtered to {len(events)} events for specific date {target_date}"
        )

    # Filter events if search terms provided and no specific date/date range was identified
    if search_terms and not (
        specific_date
        or (time_info.get("date_range_start") and time_info.get("date_range_end"))
    ):
        filtered_events = []
        search_terms_lower = [term.lower() for term in search_terms]

        for event in events:
            event_text = format_event_text(event)
            if event_text:
                event_text_lower = event_text.lower()
                # Check if any search term appears in the event
                if any(term in event_text_lower for term in search_terms_lower):
                    filtered_events.append(event)

        events = filtered_events
        search_terms_display = ", ".join(search_terms)
    else:
        # When a date is specified, don't filter by search terms
        filtered_events = events
        search_terms_display = ""

    # Format date for display
    if specific_date:
        date_display = specific_date.strftime("%A, %B %d, %Y")
    elif time_info.get("date_range_start") and time_info.get("date_range_end"):
        date_display = f"{time_info['date_range_start'].strftime('%B %d')} to {time_info['date_range_end'].strftime('%B %d, %Y')}"
    else:
        if is_past:
            date_display = (
                f"{start_time.strftime('%B %d')} to {end_time.strftime('%B %d, %Y')}"
            )
        else:
            date_display = (
                f"{start_time.strftime('%B %d')} to {end_time.strftime('%B %d, %Y')}"
            )

    # Format for display
    formatted_events = []
    for event in filtered_events:
        formatted_event = format_event_text(event)
        if formatted_event:  # Only add non-None events
            formatted_events.append(formatted_event)

    # Create a conversational message
    if len(formatted_events) == 0:
        # If no events found and using default 7-day range, offer to expand search
        if (
            not search_terms
            and not specific_date
            and not (
                time_info.get("date_range_start") and time_info.get("date_range_end")
            )
            and days_range == 7
        ):
            direction = "past" if is_past else "next"
            look_direction = "back" if is_past else "ahead"
            return {
                "status": "no_events_clarification_needed",
                "message": f"I didn't find any events in the {direction} week. How far {look_direction} would you like me to look?",
                "suggestion": "Try saying something like 'next 3 months', 'past 2 weeks', or 'entire year ahead'.",
                "events": [],
                "query": query,
                "intent_type": "search_events",
                "date": date_display,
                "days_range": days_range,
            }

        # Regular no-events messages
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
    from ...utils.llm_client import get_llm_client

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
    from ...cli.query_processor import get_calendar_list_response

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


async def follow_up_question_handler(
    query: str,
    intent_data: Dict[str, Any],
    conversation_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Handle follow-up questions by providing specific answers to the user's exact question.

    Args:
        query: User's follow-up question
        intent_data: Intent analysis data
        conversation_context: Previous conversation context

    Returns:
        Specific answer to the user's question
    """
    try:
        logger.debug(f"Processing follow-up question: {query}")

        # Get recent events that might be relevant
        calendar_service = GoogleCalendarService()

        # Use broader time range to find context
        time_info = parse_time_range("past 2 weeks to next 2 weeks")  # 4-week window

        start_date = time_info.get("date_range_start") or datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=14)
        end_date = time_info.get("date_range_end") or datetime.now().replace(
            hour=23, minute=59, second=59, microsecond=999999
        ) + timedelta(days=14)

        # Get events from the broader range
        events = await calendar_service.get_events(
            start_date=start_date, end_date=end_date, max_results=100
        )

        # Look for context in recent conversation to understand what event they're asking about
        target_event = None
        search_context = []

        if conversation_context and conversation_context.get("chat_history"):
            recent_messages = conversation_context.get("chat_history", [])[
                -4:
            ]  # Last 4 messages
            for msg in recent_messages:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "").lower()
                    search_context.extend(content.split())

        # Try to find the most relevant event based on context and query
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        # Look for events that match names or terms mentioned in recent context
        event_scores = []
        for event in events:
            score = 0
            event_text = f"{event.get('summary', '')} {event.get('description', '')} {event.get('location', '')}".lower()

            # Score based on query terms
            for term in query_terms:
                if len(term) > 2 and term in event_text:  # Only meaningful terms
                    score += 2

            # Score based on recent conversation context
            for context_word in search_context:
                if len(context_word) > 2 and context_word in event_text:
                    score += 1

            if score > 0:
                event_scores.append((event, score))

        # Sort by relevance and take the most relevant
        event_scores.sort(key=lambda x: x[1], reverse=True)

        if event_scores:
            target_event = event_scores[0][0]
            logger.debug(
                f"Found target event: {target_event.get('summary')} (score: {event_scores[0][1]})"
            )

        # Answer based on the requested detail
        requested_detail = intent_data.get("requested_detail", "none")
        question_type = intent_data.get("question_type", "none")

        if not target_event:
            return "I'm not sure which specific event you're asking about. Could you provide more details?"

        # Handle specific detail requests
        if (
            requested_detail == "zoom_link"
            or "zoom" in query_lower
            or "link" in query_lower
        ):
            # Look for zoom links in description, location, or conferenceData
            zoom_info = extract_zoom_info(target_event)
            if zoom_info:
                event_name = target_event.get("summary", "your meeting")

                # Check if it's a proper URL or just meeting info
                if zoom_info.startswith("http"):
                    if question_type == "yes_no":
                        return (
                            f"Yes! Here's the Zoom link for {event_name}: {zoom_info}"
                        )
                    else:
                        return f"Here's the Zoom link for {event_name}: {zoom_info}"
                else:
                    # It's meeting ID or other zoom info
                    if question_type == "yes_no":
                        return (
                            f"Yes! Here's the Zoom info for {event_name}: {zoom_info}"
                        )
                    else:
                        return f"Here's the Zoom info for {event_name}: {zoom_info}"
            else:
                event_name = target_event.get("summary", "that meeting")
                return f"No, I don't see a Zoom link for {event_name}."

        elif (
            requested_detail == "location"
            or "where" in query_lower
            or "location" in query_lower
        ):
            location = target_event.get("location", "")
            event_name = target_event.get("summary", "your meeting")
            if location:
                if question_type == "yes_no":
                    return f"Yes, {event_name} is at: {location}"
                else:
                    return f"{event_name} is at: {location}"
            else:
                return f"No location is specified for {event_name}."

        elif (
            requested_detail == "time" or "time" in query_lower or "when" in query_lower
        ):
            start_time = target_event.get("start", {})
            event_name = target_event.get("summary", "your meeting")

            if start_time:
                # Format the time nicely
                if "dateTime" in start_time:
                    dt = datetime.fromisoformat(
                        start_time["dateTime"].replace("Z", "+00:00")
                    )
                    formatted_time = dt.strftime("%A, %B %d, %Y at %I:%M %p")
                    return f"{event_name} is on {formatted_time}."
                elif "date" in start_time:
                    dt = datetime.strptime(start_time["date"], "%Y-%m-%d")
                    formatted_date = dt.strftime("%A, %B %d, %Y")
                    return f"{event_name} is on {formatted_date} (all day)."

            return f"I couldn't determine the time for {event_name}."

        # Handle general questions about the event
        else:
            event_name = target_event.get("summary", "your meeting")
            description = target_event.get("description", "")
            location = target_event.get("location", "")

            # Try to answer with available information
            info_parts = []
            if description:
                info_parts.append(f"Description: {description}")
            if location:
                info_parts.append(f"Location: {location}")

            zoom_info = extract_zoom_info(target_event)
            if zoom_info:
                info_parts.append(f"Zoom link: {zoom_info}")

            if info_parts:
                return f"Here's what I know about {event_name}:\n\n" + "\n".join(
                    info_parts
                )
            else:
                return (
                    f"I found {event_name} but don't have additional details available."
                )

    except Exception as e:
        logger.error(f"Error in follow-up question handler: {e}")
        return "I'm having trouble finding the information you're looking for. Could you be more specific?"


def extract_zoom_info(event: Dict[str, Any]) -> Optional[str]:
    """Extract Zoom meeting information from an event."""

    # Define improved zoom link patterns
    zoom_patterns = [
        r"https://[\w-]+\.zoom\.us/j/[\d\w?=&%\-\.]+",
        r"https://[\w-]+\.zoom\.us/s/[\d\w?=&%\-\.]+",
        r"https://[\w-]+\.zoom\.us/meeting/[\d\w?=&%\-\.]+",
        r"zoom\.us/j/[\d\w?=&%\-\.]+",
        r"zoom\.us/s/[\d\w?=&%\-\.]+",
        r"https://us\d+\.zoom\.us/j/[\d\w?=&%\-\.]+",
        r"Join Zoom Meeting\s*\n?\s*(https://[^\s]+)",
    ]

    # Check description first
    description = event.get("description", "")
    if description:
        for pattern in zoom_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                # Return just the URL, not any surrounding text
                url = match.group(1) if match.groups() else match.group(0)
                return url.strip()

    # Check location field - this is often where zoom links are placed
    location = event.get("location", "")
    if location:
        # First try to extract a proper zoom URL from location
        for pattern in zoom_patterns:
            match = re.search(pattern, location, re.IGNORECASE)
            if match:
                # Return just the URL, not any surrounding text
                url = match.group(1) if match.groups() else match.group(0)
                return url.strip()

        # If no proper URL found but location contains zoom-like text, return the location
        # This handles cases like "Zoom Meeting ID: 123-456-789" or custom zoom references
        if any(word in location.lower() for word in ["zoom", "meet", "webex", "teams"]):
            return location.strip()

    # Check conference data
    conference_data = event.get("conferenceData", {})
    if conference_data:
        entry_points = conference_data.get("entryPoints", [])
        for entry_point in entry_points:
            if entry_point.get("entryPointType") == "video":
                uri = entry_point.get("uri", "")
                if uri:
                    return uri.strip()

    return None
