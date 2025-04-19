"""
Event retrieval functionality for the calendar assistant CLI.
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta, timezone, tzlocal
import re
import dateparser
import spacy
import os

from .calendar_service import get_calendar_service
from .calendar_id_helper import resolve_calendar_id, find_matching_calendars
from .logger import get_logger

logger = get_logger(__name__)

# Dictionary to store custom date extraction processors
date_extraction_processors = {}

# Initialize spaCy NLP
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # If model not found, download it
    import subprocess

    logger.info("Downloading spaCy language model...")
    subprocess.run(
        ["python", "-m", "spacy", "download", "en_core_web_sm"],
        check=True,
        capture_output=True,
    )
    nlp = spacy.load("en_core_web_sm")


def register_date_extraction_processor(name: str, processor_func: Callable):
    """
    Register a custom date extraction processor function.

    Args:
        name: Name of the processor
        processor_func: Function that takes a query string and returns a dict with start_date and end_date
    """
    date_extraction_processors[name] = processor_func
    logger.info(f"Registered date extraction processor: {name}")


def unregister_date_extraction_processor(name: str):
    """
    Unregister a custom date extraction processor function.

    Args:
        name: Name of the processor to remove
    """
    if name in date_extraction_processors:
        del date_extraction_processors[name]
        logger.info(f"Unregistered date extraction processor: {name}")
    else:
        logger.warning(f"Attempted to unregister unknown date processor: {name}")


def get_events_in_range(
    start_time, end_time, max_total_results=500, reverse_order=False, calendar_id=None
):
    """Fetch events from Google Calendar in the given time range.

    Args:
        start_time: Start datetime
        end_time: End datetime
        max_total_results: Maximum number of total results to retrieve across all pages
        reverse_order: Whether to return events in reverse chronological order (newest first)
        calendar_id: Optional specific calendar ID or name to query. If None, query all selected and visible calendars.

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
            from .calendar_service import get_selected_calendars

            logger.info(f"Attempting to find calendar matching: '{calendar_id}'")

            # Use the helper function to find matching calendars
            matching_calendars = find_matching_calendars(service, calendar_id)

            if matching_calendars:
                # We found calendars matching the search term
                calendars_to_query = matching_calendars
                cal_names = [
                    cal.get("summaryOverride", cal.get("summary", "Unknown"))
                    for cal in matching_calendars
                ]
                logger.info(
                    f"Found {len(matching_calendars)} calendars matching '{calendar_id}': {cal_names}"
                )

                # Also log the actual IDs we'll be using
                cal_ids = [cal.get("id") for cal in matching_calendars]
                logger.info(f"Using calendar IDs: {cal_ids}")
            else:
                # No matching calendar found, fall back to primary
                all_calendars = get_selected_calendars(service)
                primary_calendar = [
                    cal for cal in all_calendars if cal.get("primary", False)
                ]
                if primary_calendar:
                    calendars_to_query = primary_calendar
                    primary_name = primary_calendar[0].get(
                        "summaryOverride",
                        primary_calendar[0].get("summary", "Unknown"),
                    )

                    logger.warning(
                        f"No calendar found matching '{calendar_id}', falling back to primary calendar: {primary_name}"
                    )
                else:
                    # If we can't even find the primary calendar, just use the first one
                    calendars_to_query = all_calendars[:1] if all_calendars else []
                    if calendars_to_query:
                        cal_name = calendars_to_query[0].get(
                            "summaryOverride",
                            calendars_to_query[0].get("summary", "Unknown"),
                        )
                        logger.warning(
                            f"No calendar found matching '{calendar_id}' and no primary calendar. "
                            f"Using {cal_name} instead."
                        )
                    else:
                        logger.error("No calendars available to query")
                        return []
        else:
            from .calendar_service import get_visible_calendars

            # Only get visibly selected calendars (checked in Google Calendar UI)
            calendars_to_query = get_visible_calendars()
            if not calendars_to_query:
                logger.debug("No visible calendars to query")
                return []

            cal_names = [cal.get("summary", "Unnamed") for cal in calendars_to_query]
            logger.info(
                f"Querying all {len(calendars_to_query)} visible calendars: {cal_names}"
            )

        all_events = []
        for calendar in calendars_to_query:
            cal_id = calendar.get("id")
            cal_name = calendar.get(
                "summaryOverride", calendar.get("summary", "Unknown")
            )

            if not cal_id:
                logger.warning(f"Skipping calendar with no ID: {cal_name}")
                continue

            try:
                # Fetch events from this calendar
                logger.debug(f"Fetching events from calendar: {cal_name} ({cal_id})")

                # IMPORTANT: Always use the calendar's ID from the calendar object
                # Never use the calendar_id parameter directly as it might just be
                # a search term like "work" and not a valid Google Calendar ID
                events_result = (
                    service.events().list(calendarId=cal_id, **params).execute()
                )
                events = events_result.get("items", [])

                # Add calendar info to each event
                for event in events:
                    event["calendarId"] = cal_id
                    # Use the human-readable calendar name that users see in Google Calendar
                    event["calendarName"] = cal_name

                all_events.extend(events)
                logger.info(
                    f"Found {len(events)} events in calendar '{cal_name}' ({cal_id})"
                )

            except Exception as e:
                logger.error(
                    f"Error fetching events from calendar '{cal_name}' ({cal_id}): {e}"
                )
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
            logger.debug(
                f"Limiting results from {len(all_events)} to {max_total_results}"
            )
            all_events = all_events[:max_total_results]

        logger.info(
            f"Returning {len(all_events)} events total across {len(calendars_to_query)} calendars"
        )
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
    if calendar_id:
        # Use the original function when a specific calendar_id is provided
        events = get_events_in_range(
            time_min,
            time_max,
            max_total_results=max_results * 10,  # Get more to filter
            calendar_id=calendar_id,
        )

        # Filter events by query if using the original function
        if query:
            filtered_events = []
            for event in events:
                event_text = (
                    f"{event.get('summary', '')} {event.get('description', '')}"
                ).lower()
                if query.lower() in event_text:
                    filtered_events.append(event)
            events = filtered_events
    else:
        # Use the new semantic search function when no specific calendar_id is provided
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "default_client_id")
        # Pass the query directly to leverage semantic search capabilities
        events = get_events_in_date_range(
            client_id,
            time_min,
            time_max,
            query=query,
        )

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

    # Use the original function for basic date range lookups
    # or implement calendar_id handling in get_events_in_date_range function
    if calendar_id:
        return get_events_in_range(
            now,
            time_max,
            max_total_results=max_results,
            calendar_id=calendar_id,
        )
    else:
        # Use the new function if no specific calendar_id is provided
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "default_client_id")
        return get_events_in_date_range(
            client_id,
            now,
            time_max,
            query=None,
        )[:max_results]


def get_past_events(
    client_id: str,
    query: Optional[str] = None,
    max_results: int = 5,
    days_back: int = 30,
    agent_state: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve events from the past matching the given query.

    Args:
        client_id: ID of the client to get events for
        query: Search query to filter events (optional)
        max_results: Maximum number of events to return
        days_back: Number of days to look back in time (default: 30)
        agent_state: Current agent state with context

    Returns:
        List of past events matching the query
    """
    # Check if the query contains keywords like "last" or "previous"
    # and extend the lookback period if it's less than a year
    if query and any(
        keyword in query.lower() for keyword in ["last", "previous", "before", "past"]
    ):
        if days_back < 365:
            days_back = 365
            logger.debug(
                f"Extended lookback period to {days_back} days for query: {query}"
            )

    # Set date range
    end_date = datetime.now().replace(hour=23, minute=59, second=59)
    start_date = end_date - timedelta(days=days_back)

    logger.debug(
        f"Searching for past events from {start_date} to {end_date} with query: {query}"
    )

    # Get all events in the date range
    events = get_events_in_date_range(client_id, start_date, end_date, query=query)

    # Sort filtered events by start time (most recent first)
    events.sort(key=lambda x: x.get("start", {}).get("dateTime", ""), reverse=True)

    return events[:max_results]


def get_events_in_date_range(
    client_id: str,
    start_date: datetime,
    end_date: datetime,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get events within a specific date range, optionally filtered by a query using semantic matching.

    Args:
        client_id: ID of the client to get events for
        start_date: Start of the date range
        end_date: End of the date range
        query: Optional search term to filter events

    Returns:
        List of events in the date range matching the query
    """
    logger.debug(f"Getting events from {start_date} to {end_date} with query: {query}")

    # Get the calendar service
    service = get_calendar_service(client_id)
    if not service:
        logger.error(f"Failed to get calendar service for client {client_id}")
        return []

    # Format dates for the API
    time_min = start_date.isoformat() + "Z"
    time_max = end_date.isoformat() + "Z"

    # Get all calendars for this user
    calendar_list = []
    try:
        page_token = None
        while True:
            calendar_list_result = (
                service.calendarList().list(pageToken=page_token).execute()
            )
            for calendar_entry in calendar_list_result.get("items", []):
                calendar_list.append(calendar_entry["id"])
            page_token = calendar_list_result.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        logger.error(f"Error retrieving calendar list: {e}")
        return []

    all_events = []

    # Get events from each calendar
    for calendar_id in calendar_list:
        try:
            events_result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            all_events.extend(events)
        except Exception as e:
            logger.error(f"Error retrieving events for calendar {calendar_id}: {e}")
            continue

    # If there's a query, filter the events using semantic matching
    if query and query.strip():
        query = query.lower().strip()
        filtered_events = []

        # Process the query with spaCy for semantic matching
        query_doc = nlp(query)

        # First try exact match
        for event in all_events:
            summary = event.get("summary", "").lower()
            description = event.get("description", "").lower()
            location = event.get("location", "").lower()

            if query in summary or query in description or query in location:
                filtered_events.append(event)
                continue  # Skip further processing if exact match found

            # Combine all event text for semantic matching
            event_text = f"{summary} {description} {location}"

            # Use spaCy for semantic matching
            event_doc = nlp(event_text)

            # Calculate semantic similarity between query and event text
            similarity = query_doc.similarity(event_doc)

            # Add event if similarity is above threshold
            if similarity > 0.6:  # Adjust threshold as needed
                event["similarity_score"] = similarity  # Store score for sorting
                filtered_events.append(event)

        # Sort filtered events by similarity score (if present) and then by date
        filtered_events.sort(
            key=lambda x: (
                -x.get("similarity_score", 0),  # Higher scores first
                x.get("start", {}).get("dateTime", x.get("start", {}).get("date", "")),
            )
        )

        return filtered_events

    return all_events


def extract_date_info(query: str) -> Optional[Dict[str, Any]]:
    """
    Extract date information from a query string.

    Args:
        query: The query string to parse for date information

    Returns:
        Dictionary with start_date and end_date if found, None otherwise
    """
    if not query:
        return None

    try:
        # First try using any registered custom processors
        for processor_name, processor_func in date_extraction_processors.items():
            try:
                logger.debug(f"Trying custom date processor: {processor_name}")
                result = processor_func(query)
                if result and "start_date" in result and "end_date" in result:
                    logger.info(
                        f"Custom processor {processor_name} extracted date info: {result}"
                    )
                    return result
            except Exception as e:
                logger.warning(f"Error in custom date processor {processor_name}: {e}")

        # Try to use NLP to extract dates
        doc = nlp(query)
        date_entities = [
            ent for ent in doc.ents if ent.label_ == "DATE" or ent.label_ == "TIME"
        ]

        # Match common date/time patterns using regex
        date_patterns = [
            # Date ranges with "to", "until", "through", etc.
            r"from\s+(.+?)\s+(?:to|until|through|till|\-)\s+(.+?)(?:\s|$)",
            # Date with time specification
            r"(?:on|at)\s+(.+?)(?:\s|$)",
            # Next/this followed by time unit (week, month, etc.)
            r"(?:next|this)\s+(\w+)",
            # Last/previous followed by time unit
            r"(?:last|previous|past)\s+(\w+)",
            # Specific dates (tomorrow, today, etc.)
            r"\b(tomorrow|today|yesterday|weekend)\b",
            # Specific day names
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        ]

        # Process date entities from spaCy if found
        if date_entities:
            # Get the date text from the first entity
            date_text = date_entities[0].text
            logger.debug(f"Found date entity: {date_text}")

            # Check for date ranges (e.g., "from Monday to Friday")
            if len(date_entities) >= 2 and any(
                w in query.lower() for w in ["to", "until", "through", "-"]
            ):
                start_text = date_entities[0].text
                end_text = date_entities[1].text

                start_date = dateparser.parse(start_text)
                end_date = dateparser.parse(end_text)

                if start_date and end_date:
                    # Make sure end date is after start date
                    if end_date < start_date:
                        # Might be a time range on the same day, set end_date to same day
                        end_date = start_date.replace(
                            hour=end_date.hour, minute=end_date.minute
                        )

                    # If end_date is still just a time (same day), add one day to include all events
                    if end_date.date() == start_date.date():
                        end_date = end_date + timedelta(days=1)

                    return {"start_date": start_date, "end_date": end_date}

            # Check for specific day names
            day_match = re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                query.lower(),
            )
            if day_match:
                day_name = day_match.group(1).capitalize()
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                day_index = [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ].index(day_name)
                days_until_day = (day_index - today.weekday()) % 7

                # Check if the query asks for "next" explicitly
                if "next" in query.lower():
                    # If explicitly asking for next week's day, add 7 days
                    days_until_day += 7
                # If the day has already passed this week, look at next week
                elif days_until_day == 0 and datetime.now().hour >= 18:
                    days_until_day = 7

                start_date = today + timedelta(days=days_until_day)
                end_date = start_date + timedelta(days=1)

                return {"start_date": start_date, "end_date": end_date}

            # Check for relative expressions
            if "today" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                return {"start_date": today, "end_date": today + timedelta(days=1)}
            elif "tomorrow" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                start_date = today + timedelta(days=1)
                return {
                    "start_date": start_date,
                    "end_date": start_date + timedelta(days=1),
                }
            elif "yesterday" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                start_date = today - timedelta(days=1)
                return {
                    "start_date": start_date,
                    "end_date": start_date + timedelta(days=1),
                }
            elif "next week" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                days_until_monday = (7 - today.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                start_date = today + timedelta(days=days_until_monday)
                end_date = start_date + timedelta(days=7)
                return {"start_date": start_date, "end_date": end_date}
            elif "this week" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                days_since_monday = today.weekday()
                start_date = today - timedelta(days=days_since_monday)
                end_date = start_date + timedelta(days=7)
                return {"start_date": start_date, "end_date": end_date}
            elif "weekend" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                days_until_saturday = (5 - today.weekday()) % 7

                # If asking for "next weekend" explicitly
                if "next" in query.lower():
                    days_until_saturday += 7
                # If it's already the weekend or after Saturday morning
                elif (today.weekday() >= 5) or (
                    today.weekday() == 5 and today.hour >= 12
                ):
                    days_until_saturday += 7

                start_date = today + timedelta(days=days_until_saturday)
                end_date = start_date + timedelta(days=2)
                return {"start_date": start_date, "end_date": end_date}
            elif "next month" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                # Get first day of next month
                if today.month == 12:
                    start_date = datetime(today.year + 1, 1, 1)
                else:
                    start_date = datetime(today.year, today.month + 1, 1)

                # Get first day of the month after next month
                if start_date.month == 12:
                    end_date = datetime(start_date.year + 1, 1, 1)
                else:
                    end_date = datetime(start_date.year, start_date.month + 1, 1)

                return {"start_date": start_date, "end_date": end_date}
            elif "this month" in query.lower():
                today = datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                # Get first day of current month
                start_date = datetime(today.year, today.month, 1)

                # Get first day of next month
                if today.month == 12:
                    end_date = datetime(today.year + 1, 1, 1)
                else:
                    end_date = datetime(today.year, today.month + 1, 1)

                return {"start_date": start_date, "end_date": end_date}

            # For other date expressions, try to parse them
            try:
                # Parse with dateparser
                parsed_date = dateparser.parse(date_text)
                if parsed_date:
                    # Check if a specific time was mentioned
                    has_time = re.search(r"\d+\s*(?:am|pm|:\d+)", date_text.lower())

                    if has_time:
                        # If specific time mentioned, don't reset the time
                        start_date = parsed_date
                        # For a time-specific query, set end_date to 2 hours later by default
                        end_date = start_date + timedelta(hours=2)
                    else:
                        # For date-only queries, set the whole day
                        start_date = parsed_date.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        end_date = start_date + timedelta(days=1)

                    return {"start_date": start_date, "end_date": end_date}
            except Exception as e:
                logger.warning(f"Failed to parse date with dateparser: {e}")

        # If spaCy didn't find a date, try other pattern matching
        for pattern in date_patterns:
            matches = re.search(pattern, query.lower())
            if matches:
                match_text = matches.group(1)
                logger.debug(f"Found date pattern match: {match_text}")

                try:
                    parsed_date = dateparser.parse(match_text)
                    if parsed_date:
                        start_date = parsed_date.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        end_date = start_date + timedelta(days=1)
                        return {"start_date": start_date, "end_date": end_date}
                except Exception as e:
                    logger.warning(f"Failed to parse date from pattern: {e}")

        # If all else fails, return None
        return None

    except Exception as e:
        logger.error(f"Error extracting date info: {e}")
        return None
