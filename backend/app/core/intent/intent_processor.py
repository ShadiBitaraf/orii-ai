"""
Intent processing functionality for the calendar assistant CLI.
"""

import logging
import time
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
from ...utils.llm_client import get_llm_client

logger = logging.getLogger(__name__)


def log_performance(
    operation: str, start_time: float, success: bool = True, error: str = None
):
    """Log performance metrics for an operation"""
    duration = time.time() - start_time
    status = "success" if success else "error"
    error_msg = f" - Error: {error}" if error else ""
    logger.info(f"Performance [{operation}] - {status} - {duration:.2f}s{error_msg}")


async def generate_llm_response(prompt: str) -> str:
    """Generate a response using the LLM."""
    start_time = time.time()
    try:
        llm_client = get_llm_client()
        response = llm_client.get_completion(prompt, model="gpt-4")
        log_performance("llm_response", start_time)
        return response.strip()
    except Exception as e:
        log_performance("llm_response", start_time, False, str(e))
        logger.error(f"Error generating LLM response: {str(e)}")
        return "I'm here to help you manage your calendar. What would you like to do?"


async def get_calendar_data(
    is_past: bool,
    days_range: int,
    reverse_chronological: bool,
    specific_date: Optional[datetime],
    date_range_start: Optional[datetime],
    date_range_end: Optional[datetime],
    specified_calendar: Optional[str],
) -> List[Dict[str, Any]]:
    """Get calendar data based on the provided parameters."""
    start_time = time.time()
    try:
        service = get_calendar_service()
        if not service:
            log_performance(
                "calendar_service", start_time, False, "Failed to get calendar service"
            )
            logger.error("Failed to get calendar service")
            return []

        # Calculate time range
        now = datetime.now(timezone.utc)
        if specific_date:
            start_time_range = specific_date
            end_time_range = specific_date + timedelta(days=1)
        elif date_range_start and date_range_end:
            start_time_range = date_range_start
            end_time_range = date_range_end
        else:
            if is_past:
                start_time_range = now - timedelta(days=days_range)
                end_time_range = now
            else:
                start_time_range = now
                end_time_range = now + timedelta(days=days_range)

        # Get events using the calendar service
        from ..calendar.event_retrieval import get_events_in_range

        events = get_events_in_range(
            start_time=start_time_range,
            end_time=end_time_range,
            max_total_results=50,
            reverse_order=reverse_chronological,
            calendar_id=specified_calendar,
        )

        log_performance("calendar_data", start_time)
        return events
    except Exception as e:
        log_performance("calendar_data", start_time, False, str(e))
        logger.error(f"Error getting calendar data: {str(e)}")
        return []


async def process_intent(
    intent_data: Dict[str, Any], query: str, conversation_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process the detected intent and generate appropriate response.
    """
    start_time = time.time()
    try:
        # Handle event creation
        if intent_data.get("intent_type") == "create_event":
            try:
                # Get calendar service
                service = get_calendar_service()

                # Extract event details from intent data
                event_details = intent_data.get("event_details", {})

                # Create the event
                created_event = create_event(service, event_details)

                # Generate a natural response about the created event
                prompt = f"""The user asked to create an event. Here are the details of the created event: {created_event}
                Generate a natural, conversational response confirming the event creation.
                Keep the response friendly and helpful."""

                response = await generate_llm_response(prompt)
                log_performance("process_intent", start_time)
                return {
                    "response": response,
                    "needs_calendar_data": False,
                    "intent_type": "create_event",
                    "calendar_data": created_event,
                    "time_info": {},
                    "llm_classification": intent_data.get("llm_classification", {}),
                }
            except Exception as e:
                logger.error(f"Error creating event: {e}")
                return {
                    "response": f"I apologize, but I encountered an error while creating the event: {str(e)}. Please try again.",
                    "needs_calendar_data": False,
                    "intent_type": "error",
                    "time_info": {},
                    "llm_classification": intent_data.get("llm_classification", {}),
                }

        # Handle follow-up questions first
        if intent_data.get("is_follow_up", False):
            # Get the last date from conversation context
            last_date = None
            if conversation_context and conversation_context.get("chat_history"):
                for msg in reversed(conversation_context["chat_history"]):
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "").lower()
                        # Look for date information in the last response
                        if (
                            "july" in content
                            or "august" in content
                            or "september" in content
                        ):
                            import re

                            date_match = re.search(
                                r"([A-Za-z]+, [A-Za-z]+ \d+, \d{4})",
                                msg.get("content", ""),
                            )
                            if date_match:
                                last_date = datetime.strptime(
                                    date_match.group(1), "%A, %B %d, %Y"
                                )
                                break

            # If we found a last date, calculate the new date based on the follow-up
            if last_date:
                # Handle "day after" or similar follow-ups
                if "day after" in query.lower() or "next day" in query.lower():
                    new_date = last_date + timedelta(days=1)
                elif "day before" in query.lower() or "previous day" in query.lower():
                    new_date = last_date - timedelta(days=1)
                else:
                    # Default to next day for simple follow-ups
                    new_date = last_date + timedelta(days=1)

                # Get events for the new date
                calendar_data = await get_calendar_data(
                    is_past=False,
                    days_range=1,
                    reverse_chronological=False,
                    specific_date=new_date,
                    date_range_start=None,
                    date_range_end=None,
                    specified_calendar=None,
                )

                # Use LLM to generate a natural response about the calendar data
                prompt = f"""The user asked about the day after their previous query. Here is their calendar data for {new_date.strftime('%A, %B %d, %Y')}: {calendar_data}
                Generate a natural, conversational response that answers their question using the calendar data.
                Keep the response friendly and helpful."""

                response = await generate_llm_response(prompt)
                log_performance("process_intent", start_time)
                return {
                    "response": response,
                    "needs_calendar_data": True,
                    "intent_type": "search_events",
                    "calendar_data": calendar_data,
                    "time_info": {"specific_date": new_date},
                    "llm_classification": intent_data.get("llm_classification", {}),
                }

        # Handle general chat and greetings
        if intent_data.get("intent_type") == "greeting":
            # Use LLM to generate a natural response
            prompt = f"""You are a friendly calendar assistant. The user has greeted you with: "{query}"
            Generate a warm, natural response that acknowledges their greeting and invites them to ask about their calendar.
            Keep the response concise and friendly."""

            response = await generate_llm_response(prompt)
            log_performance("process_intent", start_time)
            return {
                "response": response,
                "needs_calendar_data": False,
                "intent_type": "greeting",
                "time_info": {},
                "llm_classification": intent_data.get("llm_classification", {}),
            }

        # Handle calendar access queries
        if intent_data.get("intent_type") == "calendar_access_query":
            # Use LLM to generate a natural response about calendar access
            prompt = f"""The user has asked about calendar access with the query: "{query}"
            Generate a natural response explaining that you can access their Google Calendar and help them find events.
            Keep the response friendly and informative."""

            response = await generate_llm_response(prompt)
            log_performance("process_intent", start_time)
            return {
                "response": response,
                "needs_calendar_data": False,
                "intent_type": "calendar_access_query",
                "time_info": {},
                "llm_classification": intent_data.get("llm_classification", {}),
            }

        # For calendar searches, use the existing logic
        if intent_data.get("needs_calendar_data", False):
            # Get calendar data
            calendar_data = await get_calendar_data(
                intent_data.get("is_past", False),
                intent_data.get("days_range", 7),
                intent_data.get("reverse_chronological", False),
                intent_data.get("specific_date"),
                intent_data.get("date_range_start"),
                intent_data.get("date_range_end"),
                intent_data.get("specified_calendar"),
            )

            # Use LLM to generate a natural response about the calendar data
            prompt = f"""The user asked: "{query}"
            Here is their calendar data: {calendar_data}
            Generate a natural, conversational response that answers their question using the calendar data.
            Keep the response friendly and helpful."""

            response = await generate_llm_response(prompt)
            log_performance("process_intent", start_time)
            return {
                "response": response,
                "needs_calendar_data": True,
                "intent_type": "search_events",
                "calendar_data": calendar_data,
                "time_info": intent_data.get("time_info", {}),
                "llm_classification": intent_data.get("llm_classification", {}),
            }

        # For any other intents, use LLM to generate a natural response
        prompt = f"""The user asked: "{query}"
        Generate a natural, helpful response that acknowledges their question and offers assistance.
        Keep the response friendly and concise."""

        response = await generate_llm_response(prompt)
        log_performance("process_intent", start_time)
        return {
            "response": response,
            "needs_calendar_data": False,
            "intent_type": intent_data.get("intent_type", "general"),
            "time_info": intent_data.get("time_info", {}),
            "llm_classification": intent_data.get("llm_classification", {}),
        }

    except Exception as e:
        log_performance("process_intent", start_time, False, str(e))
        logger.error(f"Error processing intent: {str(e)}")
        return {
            "response": "I apologize, but I encountered an error while processing your request. Could you please try again?",
            "needs_calendar_data": False,
            "intent_type": "error",
            "time_info": {},
            "llm_classification": intent_data.get("llm_classification", {}),
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

        # Extract time context from the intent data
        time_context = intent_data.get("time_context", {})
        last_time_direction = time_context.get("last_time_direction")
        last_query = time_context.get("last_query", "")
        last_response = time_context.get("last_response", "")

        # Handle time-based follow-ups
        time_indicators = {
            "next": 1,
            "after": 1,
            "later": 1,
            "previous": -1,
            "before": -1,
            "earlier": -1,
            "last": -1,
            "first": -1,
        }

        query_lower = query.lower()
        time_shift = 0
        time_unit = "day"

        # Check for time shift indicators
        for indicator, shift in time_indicators.items():
            if indicator in query_lower:
                time_shift = shift
                # Check for time unit
                if "week" in query_lower:
                    time_unit = "week"
                elif "month" in query_lower:
                    time_unit = "month"
                elif "year" in query_lower:
                    time_unit = "year"
                break

        # If we found a time shift, calculate the new date
        if time_shift != 0:
            from datetime import datetime, timedelta

            current_date = datetime.now()

            if time_unit == "day":
                new_date = current_date + timedelta(days=time_shift)
            elif time_unit == "week":
                new_date = current_date + timedelta(weeks=time_shift)
            elif time_unit == "month":
                # Approximate month as 30 days
                new_date = current_date + timedelta(days=30 * time_shift)
            elif time_unit == "year":
                new_date = current_date + timedelta(days=365 * time_shift)

            # Format the response
            formatted_date = new_date.strftime("%A, %B %d, %Y")
            return f"{formatted_date}"

        # If no time shift found, try to find context in recent conversation
        if conversation_context and conversation_context.get("chat_history"):
            recent_messages = conversation_context.get("chat_history", [])[
                -4:
            ]  # Last 4 messages
            for msg in recent_messages:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "").lower()
                    # Look for date/time information in the last response
                    if "today is" in content or "current time" in content:
                        # Extract the date from the previous response
                        import re

                        date_match = re.search(
                            r"([A-Za-z]+, [A-Za-z]+ \d+, \d{4})", msg.get("content", "")
                        )
                        if date_match:
                            base_date = datetime.strptime(
                                date_match.group(1), "%A, %B %d, %Y"
                            )
                            # Apply the time shift
                            if time_shift != 0:
                                if time_unit == "day":
                                    new_date = base_date + timedelta(days=time_shift)
                                elif time_unit == "week":
                                    new_date = base_date + timedelta(weeks=time_shift)
                                elif time_unit == "month":
                                    new_date = base_date + timedelta(
                                        days=30 * time_shift
                                    )
                                elif time_unit == "year":
                                    new_date = base_date + timedelta(
                                        days=365 * time_shift
                                    )
                                return new_date.strftime("%A, %B %d, %Y")

        # If we couldn't determine the date, try to get events from calendar
        calendar_service = get_calendar_service()
        time_info = parse_time_range("past 2 weeks to next 2 weeks")

        start_date = time_info.get("date_range_start") or datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=14)
        end_date = time_info.get("date_range_end") or datetime.now().replace(
            hour=23, minute=59, second=59, microsecond=999999
        ) + timedelta(days=14)

        events = await calendar_service.get_events(
            start_date=start_date, end_date=end_date, max_results=100
        )

        # If we have events, try to find the most relevant one
        if events:
            # Sort events by start time
            events.sort(key=lambda x: x.get("start", {}).get("dateTime", ""))

            # If asking about next/previous, return the next/previous event
            if time_shift > 0:
                for event in events:
                    if (
                        event.get("start", {}).get("dateTime", "")
                        > datetime.now().isoformat()
                    ):
                        return f"The next event is {event.get('summary')} on {event.get('start', {}).get('dateTime', '')}"
            elif time_shift < 0:
                for event in reversed(events):
                    if (
                        event.get("start", {}).get("dateTime", "")
                        < datetime.now().isoformat()
                    ):
                        return f"The previous event was {event.get('summary')} on {event.get('start', {}).get('dateTime', '')}"

        return "I'm not sure which specific time period you're asking about. Could you please be more specific?"

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
