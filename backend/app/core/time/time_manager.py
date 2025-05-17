"""
Unified time management module for the calendar assistant CLI.

This module combines functionality from time_utils.py and time_parsing.py to eliminate
overlap and provide a cleaner interface for all time-related operations.
"""

import re
import logging
import pytz
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timedelta, date, time

import dateparser

logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEZONE = "UTC"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_TIME_FORMAT = "%H:%M:%S"
DEFAULT_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# Common time expressions
TIME_EXPRESSIONS = {
    "today": 0,
    "tomorrow": 1,
    "yesterday": -1,
    "day after tomorrow": 2,
    "day before yesterday": -2,
    "next week": 7,
    "last week": -7,
    "next month": 30,
    "last month": -30,
}

# Regex patterns for time parsing
TIME_RANGE_PATTERNS = [
    # Example: "last 3 days" or "next 5 weeks"
    r"(last|next)\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)",
    # Example: "past 2 days" or "coming 3 weeks"
    r"(past|coming|previous|upcoming)\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)",
    # Example: "3 days ago" or "2 weeks from now"
    r"(\d+)\s+(day|days|week|weeks|month|months|year|years)\s+(ago|from now)",
]


def parse_time_range(query: str) -> Dict[str, Any]:
    """Parse a time range from a query string.

    Args:
        query: Text to parse

    Returns:
        Dictionary with time range information including:
        - is_past: Boolean indicating if looking for past events
        - days_range: Number of days to look ahead/back
        - specific_date: Specific date if mentioned
        - reverse_chronological: Whether results should be in reverse chronological order
    """
    query = query.lower()
    result = {
        "is_past": False,
        "days_range": 7,  # Default to one week
        "reverse_chronological": False,
        "specific_date": None,
    }

    # Check for past vs. future indicators
    past_indicators = ["last", "past", "previous", "ago", "recent", "before", "history"]
    future_indicators = ["next", "upcoming", "future", "coming", "after", "from now"]

    # Determine if query is about past or future
    if any(indicator in query for indicator in past_indicators):
        result["is_past"] = True
        result["reverse_chronological"] = True  # Past events usually shown newest first
    elif any(indicator in query for indicator in future_indicators):
        result["is_past"] = False

    # Check for specific time ranges using regex patterns
    for pattern in TIME_RANGE_PATTERNS:
        matches = re.search(pattern, query)
        if matches:
            groups = matches.groups()

            # Extract the numeric value
            if len(groups) >= 2:
                try:
                    numeric_value = int(groups[1])
                    unit = groups[2].lower()

                    # Convert to days based on unit
                    if unit in ("day", "days"):
                        result["days_range"] = numeric_value
                    elif unit in ("week", "weeks"):
                        result["days_range"] = numeric_value * 7
                    elif unit in ("month", "months"):
                        result["days_range"] = numeric_value * 30
                    elif unit in ("year", "years"):
                        result["days_range"] = numeric_value * 365

                    logger.debug(
                        f"Found time range: {numeric_value} {unit} = {result['days_range']} days"
                    )
                    break
                except (ValueError, TypeError):
                    pass

    # Try to extract a specific date using dateparser
    try:
        # Common date patterns to look for
        date_patterns = [
            r"\b(?:on\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*\d{4})?\b",
            r"\b(?:on\s+)?(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s*,?\s*\d{4})?\b",
            r"\b(?:on\s+)?\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
            r"\b(?:on\s+)?\d{4}-\d{1,2}-\d{1,2}\b",
            r"\b(?:on\s+)?(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
            r"\b(?:on\s+)?tomorrow\b",
            r"\b(?:on\s+)?yesterday\b",
            r"\b(?:on\s+)?today\b",
        ]

        # Extract date expressions from query
        date_expr = None
        for pattern in date_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                date_expr = match.group(0)
                # Remove 'on' prefix if present
                date_expr = re.sub(r"^on\s+", "", date_expr)
                break

        if date_expr:
            logger.debug(f"Found date expression: {date_expr}")

            # Use dateparser to interpret the expression
            parsed_date = dateparser.parse(date_expr)
            if parsed_date:
                result["specific_date"] = parsed_date
                logger.debug(f"Parsed specific date: {parsed_date}")
    except Exception as e:
        logger.error(f"Error parsing specific date: {e}")

    return result


def parse_natural_language_datetime(text: str) -> Dict[str, Any]:
    """Parse natural language date and time into structured format.

    Args:
        text: Natural language date/time text

    Returns:
        Dictionary with parsed datetime information
    """
    text = text.lower()
    result = {
        "start_datetime": None,
        "end_datetime": None,
        "is_all_day": False,
        "timezone": DEFAULT_TIMEZONE,
    }

    # Check for all-day indicators
    all_day_indicators = ["all day", "all-day", "allday", "full day", "whole day"]
    result["is_all_day"] = any(indicator in text for indicator in all_day_indicators)

    # Parse start time
    try:
        # Try to parse the text as a datetime
        parsed_datetime = dateparser.parse(text)
        if parsed_datetime:
            result["start_datetime"] = parsed_datetime

            # If it's all day, set to midnight
            if result["is_all_day"]:
                result["start_datetime"] = result["start_datetime"].replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

            # Default end time is 1 hour later if not all day
            if not result["is_all_day"]:
                result["end_datetime"] = result["start_datetime"] + timedelta(hours=1)
            else:
                # For all-day, end datetime is end of the day
                result["end_datetime"] = result["start_datetime"].replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
    except Exception as e:
        logger.error(f"Error parsing natural language datetime: {e}")

    return result


def format_datetime_range(
    start: Union[str, datetime], end: Union[str, datetime], is_all_day: bool = False
) -> str:
    """Format a datetime range for display.

    Args:
        start: Start datetime (string or datetime object)
        end: End datetime (string or datetime object)
        is_all_day: Whether this is an all-day event

    Returns:
        Formatted datetime range string
    """
    # Convert string datetimes to datetime objects if needed
    if isinstance(start, str):
        start = dateparser.parse(start)
    if isinstance(end, str):
        end = dateparser.parse(end)

    # If either datetime parsing failed, return a message
    if not start or not end:
        return "Time not specified"

    # For all-day events
    if is_all_day:
        # If same day
        if start.date() == end.date():
            return f"All day on {start.strftime('%A, %B %d, %Y')}"
        # Multiple days
        return f"{start.strftime('%A, %B %d, %Y')} to {end.strftime('%A, %B %d, %Y')}"

    # Same day, different times
    if start.date() == end.date():
        return f"{start.strftime('%A, %B %d, %Y')} from {start.strftime('%I:%M %p')} to {end.strftime('%I:%M %p')}"

    # Different days
    return f"{start.strftime('%A, %B %d, %Y at %I:%M %p')} to {end.strftime('%A, %B %d, %Y at %I:%M %p')}"


def convert_to_timezone(dt: datetime, target_timezone: str) -> datetime:
    """Convert a datetime to a different timezone.

    Args:
        dt: Datetime to convert
        target_timezone: Target timezone (e.g., 'America/New_York')

    Returns:
        Datetime in the target timezone
    """
    # If datetime is naive, assume it's in UTC
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    # Convert to target timezone
    target_tz = pytz.timezone(target_timezone)
    return dt.astimezone(target_tz)


def extract_date_range_from_query(
    query: str,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Extract explicit date range from a query.

    Args:
        query: Query string

    Returns:
        Tuple of (start_date, end_date) or (None, None) if no range found
    """
    # Common patterns for date ranges
    patterns = [
        # "from May 1 to May 5"
        r"from\s+(.*?)\s+to\s+(.*)",
        # "between June 10 and June 15"
        r"between\s+(.*?)\s+and\s+(.*)",
        # "June 1-5"
        r"([a-zA-Z]+\s+\d{1,2})\s*[-–—]\s*(\d{1,2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            start_text, end_text = match.groups()

            # Parse start date
            start_date = dateparser.parse(start_text)

            # For patterns like "June 1-5" where end is just a day number
            if re.match(r"^\d{1,2}$", end_text.strip()):
                # End date should use same month/year as start
                if start_date:
                    # Create end date with same month/year but different day
                    try:
                        day = int(end_text.strip())
                        end_date = start_date.replace(day=day)

                        # If end date is before start date, it's likely next month
                        if end_date < start_date:
                            # Move to next month
                            if end_date.month == 12:
                                end_date = end_date.replace(
                                    year=end_date.year + 1, month=1
                                )
                            else:
                                end_date = end_date.replace(month=end_date.month + 1)
                    except ValueError:
                        # Invalid day for month
                        end_date = None
                else:
                    end_date = None
            else:
                # Normal case - parse full end date
                end_date = dateparser.parse(end_text)

            # Set time to beginning/end of day if just dates
            if start_date:
                start_date = start_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            if end_date:
                end_date = end_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            logger.debug(f"Extracted date range: {start_date} to {end_date}")
            return start_date, end_date

    # No date range found
    return None, None


def is_weekend(dt: datetime) -> bool:
    """Check if a datetime is on a weekend.

    Args:
        dt: Datetime to check

    Returns:
        True if weekend, False otherwise
    """
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday


def get_next_workday(dt: datetime) -> datetime:
    """Get the next workday from a given datetime.

    Args:
        dt: Starting datetime

    Returns:
        Next workday
    """
    # Move to next day
    next_day = dt + timedelta(days=1)

    # Skip weekends
    while is_weekend(next_day):
        next_day += timedelta(days=1)

    return next_day


def get_relative_date(base_date: datetime, days_offset: int) -> datetime:
    """Get a date relative to a base date.

    Args:
        base_date: Base datetime
        days_offset: Offset in days (positive or negative)

    Returns:
        Relative datetime
    """
    return base_date + timedelta(days=days_offset)


def is_same_day(dt1: datetime, dt2: datetime) -> bool:
    """Check if two datetimes are on the same day.

    Args:
        dt1: First datetime
        dt2: Second datetime

    Returns:
        True if same day, False otherwise
    """
    return dt1.date() == dt2.date()


def format_duration(minutes: int) -> str:
    """Format a duration in minutes to a human-readable string.

    Args:
        minutes: Duration in minutes

    Returns:
        Formatted duration string
    """
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if remaining_minutes == 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"

    return f"{hours} hour{'s' if hours != 1 else ''} {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"
