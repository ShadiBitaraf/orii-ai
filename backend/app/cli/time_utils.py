"""
Time and date parsing utilities for the CLI application.
"""

import re
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta


def parse_time_range(query):
    """Parse time range from query text

    Args:
        query: Natural language query string

    Returns:
        Dict with parsed time range info
    """
    # Default values
    is_past = False
    days_range = 7  # Default to a week
    reverse_chronological = False
    specific_date = None

    query_lower = query.lower()
    print(f"[DEBUG] TIME PARSING - Analyzing query for time range: '{query_lower}'")

    # Try to extract a specific date first (this takes precedence)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Various date formats to check
    date_patterns = [
        # May 18
        r"(?:on|for|at|next|this|coming|past|previous|last)\s+([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?",
        # 18th of May
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)(?:\s*,?\s*(\d{4}))?",
        # MM/DD or MM/DD/YYYY
        r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?",
        # YYYY-MM-DD format
        r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})",
    ]

    year = today.year
    for pattern in date_patterns:
        matches = re.findall(pattern, query_lower)
        if matches:
            print(f"[DEBUG] TIME PARSING - Found date pattern matches: {matches}")

            for match in matches:
                try:
                    # Handle different pattern formats
                    if len(match) == 3:  # Full patterns with possible year
                        if pattern == date_patterns[0]:  # Month name, day, [year]
                            month_str = match[0]
                            day = int(match[1])
                            year_str = match[2]
                        elif pattern == date_patterns[1]:  # Day, month name, [year]
                            day = int(match[0])
                            month_str = match[1]
                            year_str = match[2]
                        elif pattern == date_patterns[2]:  # MM/DD/[YY]
                            # For MM/DD format
                            month = int(match[0])
                            day = int(match[1])
                            year_str = match[2]
                            month_str = None
                        else:  # YYYY-MM-DD
                            year = int(match[0])
                            month = int(match[1])
                            day = int(match[2])
                            month_str = None

                        # Parse year if provided
                        if year_str and year_str.strip():
                            year = int(year_str)
                            # Handle 2-digit years
                            if year < 100:
                                year += 2000

                    # Handle month names
                    if "month_str" in locals() and month_str:
                        month_mappings = {
                            "jan": 1,
                            "january": 1,
                            "feb": 2,
                            "february": 2,
                            "mar": 3,
                            "march": 3,
                            "apr": 4,
                            "april": 4,
                            "may": 5,
                            "jun": 6,
                            "june": 6,
                            "jul": 7,
                            "july": 7,
                            "aug": 8,
                            "august": 8,
                            "sep": 9,
                            "september": 9,
                            "sept": 9,
                            "oct": 10,
                            "october": 10,
                            "nov": 11,
                            "november": 11,
                            "dec": 12,
                            "december": 12,
                        }

                        # Try to match the month name
                        matched_month = None
                        for month_name, month_num in month_mappings.items():
                            if month_str.startswith(month_name):
                                matched_month = month_num
                                break

                        if matched_month:
                            month = matched_month
                        else:
                            print(
                                f"[DEBUG] TIME PARSING - Could not parse month name: {month_str}"
                            )
                            continue

                    # Create the date object
                    try:
                        parsed_date = datetime(year, month, day)
                        if parsed_date:
                            specific_date = parsed_date
                            print(
                                f"[DEBUG] TIME PARSING - Found specific date: {specific_date}"
                            )

                            # Check if the date is in the past or future
                            is_past = specific_date < today

                            # For specific dates, we only look at events for that day
                            days_range = 1
                            break
                    except ValueError as e:
                        print(f"[DEBUG] TIME PARSING - Invalid date values: {e}")
                except Exception as e:
                    print(f"[DEBUG] TIME PARSING - Error parsing date: {e}")

    # If we found a specific date, no need to process other time indicators
    if not specific_date:
        # Count indicators of past vs future tense
        past_indicators = len(
            [
                word
                for word in [
                    "last",
                    "previous",
                    "past",
                    "recent",
                    "ago",
                    "yesterday",
                    "earlier",
                    "before",
                    "had",
                    "was",
                    "were",
                ]
                if word in query_lower
            ]
        )

        future_indicators = len(
            [
                word
                for word in [
                    "next",
                    "upcoming",
                    "future",
                    "coming",
                    "soon",
                    "tomorrow",
                    "later",
                    "after",
                    "will",
                    "plan",
                    "schedule",
                ]
                if word in query_lower
            ]
        )

        print(
            f"[DEBUG] TIME PARSING - Past indicators: {past_indicators}, Future indicators: {future_indicators}"
        )

        # Determine if past or future based on query indicators
        if past_indicators > future_indicators:
            is_past = True

        # Extract days range for the search
        day_match = re.search(r"(\d+)\s+days?", query_lower)
        week_match = re.search(r"(\d+)\s+weeks?", query_lower)
        month_match = re.search(r"(\d+)\s+months?", query_lower)

        if day_match:
            days_range = int(day_match.group(1))
        elif week_match:
            days_range = int(week_match.group(1)) * 7
        elif month_match:
            days_range = int(month_match.group(1)) * 30
        else:
            # Look for specific time phrases
            if any(phrase in query_lower for phrase in ["today", "tonight"]):
                days_range = 1
                print(
                    "[DEBUG] TIME PARSING - Found 'today' or 'tonight', setting range to 1 day"
                )
            elif "tomorrow" in query_lower:
                days_range = 2  # Today + tomorrow
                print(
                    "[DEBUG] TIME PARSING - Found 'tomorrow', setting range to 2 days"
                )
            elif "yesterday" in query_lower:
                is_past = True
                days_range = 2  # Today + yesterday
                print(
                    "[DEBUG] TIME PARSING - Found 'yesterday', setting range to 2 days (past)"
                )
            elif "this week" in query_lower:
                days_range = 7
                print(
                    "[DEBUG] TIME PARSING - Found 'this week', setting range to 7 days"
                )
            elif "next week" in query_lower:
                days_range = 14  # Covers this week + next week
                print(
                    "[DEBUG] TIME PARSING - Found 'next week', setting range to 14 days"
                )
            elif "last week" in query_lower:
                is_past = True
                days_range = 14  # Covers this week + last week
                print(
                    "[DEBUG] TIME PARSING - Found 'last week', setting range to 14 days (past)"
                )
            elif "this month" in query_lower:
                days_range = 30
                print(
                    "[DEBUG] TIME PARSING - Found 'this month', setting range to 30 days"
                )
            else:
                print(
                    "[DEBUG] TIME PARSING - No specific temporal phrases found, using defaults"
                )

        # Special handling for queries looking for recent/last events
        if any(word in query_lower for word in ["recent", "last", "latest"]):
            reverse_chronological = True
            print(
                "[DEBUG] TIME PARSING - Found 'recent/last/latest', enabling reverse chronological order"
            )
            # For "last" queries, we should look much further back
            if is_past:
                days_range = 365  # Look back a full year for "last" queries
                print(
                    "[DEBUG] TIME PARSING - 'last' query with past context, extending days_range to 365 days"
                )

    print(
        f"[DEBUG] TIME PARSING - Final result: is_past={is_past}, days_range={days_range}, reverse_chronological={reverse_chronological}"
    )

    result = {
        "is_past": is_past,
        "days_range": days_range,
        "reverse_chronological": reverse_chronological,
    }

    # Add specific date if found
    if specific_date:
        result["specific_date"] = specific_date

    return result


def parse_natural_language_datetime(text, default_days=7, default_duration_hours=1):
    """
    Parse natural language date/time from text using dateutil's parser with enhanced context.

    Args:
        text: The text containing date/time information
        default_days: Default number of days to look ahead if no specific date found
        default_duration_hours: Default duration for events in hours

    Returns:
        Dictionary with extracted date and time information
    """
    result = {
        "start_datetime": None,
        "end_datetime": None,
        "is_all_day": False,
        "date_specified": False,
        "time_specified": False,
        "duration_specified": False,
        "duration_hours": default_duration_hours,
    }

    if not text:
        return result

    # Use current date/time as the default
    base_time = datetime.now()

    # Common time expressions
    time_range_patterns = [
        r"from\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+to\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
    ]

    # Duration patterns
    duration_patterns = [
        r"for\s+(\d+)\s+hour",
        r"for\s+(\d+)\s+minute",
        r"(\d+)\s+hour\s+(?:long|duration)",
        r"(\d+)\s+minute\s+(?:long|duration)",
    ]

    # Special date handling for common terms
    if re.search(r"\b(today|tonight)\b", text, re.IGNORECASE):
        result["start_datetime"] = base_time
        result["date_specified"] = True

    elif re.search(r"\btomorrow\b", text, re.IGNORECASE):
        result["start_datetime"] = base_time + timedelta(days=1)
        result["date_specified"] = True

    elif re.search(r"\bin\s+(\d+)\s+days?\b", text, re.IGNORECASE):
        days_match = re.search(r"\bin\s+(\d+)\s+days?\b", text, re.IGNORECASE)
        if days_match:
            days = int(days_match.group(1))
            result["start_datetime"] = base_time + timedelta(days=days)
            result["date_specified"] = True

    elif re.search(r"\bnext\s+(week|month)\b", text, re.IGNORECASE):
        unit_match = re.search(r"\bnext\s+(week|month)\b", text, re.IGNORECASE)
        if unit_match:
            unit = unit_match.group(1).lower()
            if unit == "week":
                result["start_datetime"] = base_time + timedelta(days=7)
            else:  # month
                result["start_datetime"] = base_time + relativedelta(months=1)
            result["date_specified"] = True

    # Check for specific weekdays
    weekday_match = re.search(
        r"\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        text,
        re.IGNORECASE,
    )
    if weekday_match:
        is_next = weekday_match.group(1) is not None
        day_name = weekday_match.group(2).lower()
        day_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_day = day_map[day_name]
        days_ahead = target_day - base_time.weekday()

        if (
            days_ahead <= 0 or is_next
        ):  # If the day has passed this week or specifically "next"
            days_ahead += 7

        result["start_datetime"] = base_time + timedelta(days=days_ahead)
        result["date_specified"] = True

    # If we haven't set a date yet, try to use dateutil parser
    if not result["date_specified"]:
        try:
            # Try to extract a date using dateutil parser
            parsed_date = date_parser.parse(text, fuzzy=True, default=base_time)

            # Only accept the date if it's not just returning the default (today)
            if parsed_date.date() != base_time.date() or "today" in text.lower():
                result["start_datetime"] = parsed_date
                result["date_specified"] = True
        except:
            # If parsing fails, don't set any date
            pass

    # Check for time range expressions
    for pattern in time_range_patterns:
        time_match = re.search(pattern, text, re.IGNORECASE)
        if time_match:
            result["time_specified"] = True
            if len(time_match.groups()) == 2:  # Start and end time
                try:
                    start_time_str = time_match.group(1)
                    end_time_str = time_match.group(2)

                    # Parse times and attach to the date we found or today's date
                    base_date = (
                        result["start_datetime"].date()
                        if result["start_datetime"]
                        else base_time.date()
                    )

                    start_time = date_parser.parse(start_time_str).time()
                    end_time = date_parser.parse(end_time_str).time()

                    start_dt = datetime.combine(base_date, start_time)
                    end_dt = datetime.combine(base_date, end_time)

                    # If end time is earlier than start time, assume it's the next day
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)

                    result["start_datetime"] = start_dt
                    result["end_datetime"] = end_dt
                    result["duration_hours"] = (
                        end_dt - start_dt
                    ).total_seconds() / 3600
                    result["duration_specified"] = True
                    break
                except:
                    pass
            elif len(time_match.groups()) == 1:  # Only start time
                try:
                    start_time_str = time_match.group(1)
                    base_date = (
                        result["start_datetime"].date()
                        if result["start_datetime"]
                        else base_time.date()
                    )

                    start_time = date_parser.parse(start_time_str).time()
                    start_dt = datetime.combine(base_date, start_time)

                    result["start_datetime"] = start_dt
                    result["end_datetime"] = start_dt + timedelta(
                        hours=default_duration_hours
                    )
                    break
                except:
                    pass

    # Check for duration patterns if we have a start time but no end time yet
    if result["start_datetime"] and not result["duration_specified"]:
        for pattern in duration_patterns:
            duration_match = re.search(pattern, text, re.IGNORECASE)
            if duration_match:
                try:
                    duration_value = int(duration_match.group(1))
                    if "hour" in pattern:
                        duration_hours = duration_value
                    else:  # minutes
                        duration_hours = duration_value / 60

                    result["duration_hours"] = duration_hours
                    result["duration_specified"] = True
                    result["end_datetime"] = result["start_datetime"] + timedelta(
                        hours=duration_hours
                    )
                    break
                except:
                    pass

    # If we have a start time but no end time, apply default duration
    if result["start_datetime"] and not result["end_datetime"]:
        result["end_datetime"] = result["start_datetime"] + timedelta(
            hours=default_duration_hours
        )

    # Check for all-day event indicators
    if re.search(r"\ball[\s-]day\b", text, re.IGNORECASE):
        result["is_all_day"] = True

        # If we have a date, adjust times to be all day
        if result["start_datetime"]:
            start_date = result["start_datetime"].date()
            result["start_datetime"] = datetime.combine(start_date, datetime.min.time())
            result["end_datetime"] = datetime.combine(start_date, datetime.max.time())

    # If we still don't have a start_datetime after all processing, use defaults
    if not result["start_datetime"]:
        # Default to tomorrow
        result["start_datetime"] = base_time + timedelta(days=1)
        result["end_datetime"] = result["start_datetime"] + timedelta(
            hours=default_duration_hours
        )

    # Ensure both datetimes have timezone info if possible
    local_tz = datetime.now().astimezone().tzinfo
    if result["start_datetime"] and result["start_datetime"].tzinfo is None:
        result["start_datetime"] = result["start_datetime"].replace(tzinfo=local_tz)
    if result["end_datetime"] and result["end_datetime"].tzinfo is None:
        result["end_datetime"] = result["end_datetime"].replace(tzinfo=local_tz)

    return result


def format_datetime_range(start_time, end_time, is_all_day=False):
    """Format start and end times for an event in a readable format.

    Args:
        start_time: Start time string (ISO format)
        end_time: End time string (ISO format)
        is_all_day: Whether this is an all-day event

    Returns:
        Formatted string with the date/time range
    """
    if is_all_day:
        # Parse dates and format all-day events
        try:
            start_date = datetime.fromisoformat(start_time)
            end_date = datetime.fromisoformat(end_time)
            # End date is exclusive in all-day events, so subtract a day for display
            end_date = end_date - timedelta(days=1)

            # Same day
            if start_date.date() == end_date.date():
                return f"{start_date.strftime('%Y-%m-%d')} (All day)"
            else:
                return f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')} (All day)"
        except (ValueError, TypeError):
            return f"{start_time} - {end_time} (All day)"
    else:
        # Parse and format timed events
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

            # Convert to local time for display
            local_tz = datetime.now().astimezone().tzinfo
            start_local = start_dt.astimezone(local_tz)
            end_local = end_dt.astimezone(local_tz)

            # Same day
            if start_local.date() == end_local.date():
                return f"{start_local.strftime('%Y-%m-%d %I:%M %p')} - {end_local.strftime('%I:%M %p')}"
            else:
                return f"{start_local.strftime('%Y-%m-%d %I:%M %p')} - {end_local.strftime('%Y-%m-%d %I:%M %p')}"
        except (ValueError, TypeError):
            return f"{start_time} - {end_time}"
