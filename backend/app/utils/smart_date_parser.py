"""
Advanced date and time parsing system with context awareness.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
import dateparser
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
import json

# Get the application logger
from .logger import get_logger

logger = get_logger()

# Import the LLM client if available
try:
    from .llm_client import get_llm_client
except ImportError:
    logger.warning("LLM client not available, falling back to regex patterns")
    get_llm_client = None


class SmartDateParser:
    """
    Smart date and time parser that combines multiple approaches:
    1. LLM-powered natural language understanding
    2. Context-aware date resolution
    3. Specialized libraries like dateparser
    4. Pattern-based fallbacks
    """

    def __init__(self):
        self.reference_date = datetime.now()
        self.last_mentioned_date = None
        self.conversation_references = []
        self.llm_client = None

        # Initialize LLM client if available
        if get_llm_client:
            try:
                self.llm_client = get_llm_client()
                logger.info("LLM client initialized for SmartDateParser")
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {e}")

        # Common time frames with their approximate day ranges
        self.time_frames = {
            "day": 1,
            "week": 7,
            "fortnight": 14,
            "month": 30,
            "quarter": 90,
            "year": 365,
        }

    def update_conversation_context(self, date_obj: datetime):
        """Update the conversation context with a new date reference"""
        self.last_mentioned_date = date_obj
        self.conversation_references.append(date_obj)
        if len(self.conversation_references) > 5:  # Keep last 5 references
            self.conversation_references.pop(0)

    def seems_future_oriented(self, query: str) -> bool:
        """Determine if a query seems to be oriented toward the future"""
        query_lower = query.lower()

        future_indicators = [
            "will",
            "going to",
            "plan",
            "upcoming",
            "future",
            "next",
            "coming",
            "soon",
            "tomorrow",
            "later",
            "schedule",
            "ahead",
        ]

        past_indicators = [
            "was",
            "did",
            "had",
            "past",
            "previous",
            "ago",
            "earlier",
            "yesterday",
            "last",
            "before",
            "recent",
            "recently",
        ]

        future_count = sum(1 for word in future_indicators if word in query_lower)
        past_count = sum(1 for word in past_indicators if word in query_lower)

        return future_count > past_count

    def _parse_last_n_days_pattern(self, query, now):
        """
        Parse patterns like "last three days", "past 5 days", "recent week", etc.

        Args:
            query: The query string
            now: Current datetime for reference

        Returns:
            Dict with date range info if matched, None otherwise
        """
        # Enhanced patterns for "last N days" type queries
        patterns = [
            # Standard patterns
            r"(?i)(?:last|past|previous)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|hundred)\s+(day|days|week|weeks|month|months|year|years)",
            r"(?i)(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|hundred)\s+(day|days|week|weeks|month|months|year|years)\s+(?:ago|back)",
            # More flexible patterns
            r"(?i)(?:in\s+)?(?:the\s+)?(?:last|past|previous)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|hundred)\s+(day|days|week|weeks|month|months|year|years)",
            r"(?i)(?:from|for|during|within|over)(?:\s+the)?\s+(?:last|past|previous)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|hundred)\s+(day|days|week|weeks|month|months|year|years)",
            # Approximate time references
            r"(?i)(?:last|past|previous|recent)\s+(few|couple|several)\s+(day|days|week|weeks|month|months|year|years)",
            r"(?i)(?:in|from|for|during|within)(?:\s+the)?\s+(?:last|past|previous|recent)\s+(few|couple|several)\s+(day|days|week|weeks|month|months|year|years)",
            # Single unit references
            r"(?i)(?:last|past|previous|recent)\s+(day|week|month|fortnight|quarter|year)",
            r"(?i)(?:within|during|over|for|from)(?:\s+the)?\s+(?:last|past|previous|recent)\s+(day|week|month|fortnight|quarter|year)",
        ]

        # Extended number word to digit mapping
        word_to_number = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "hundred": 100,
            "few": 3,
            "couple": 2,
            "several": 4,  # Approximate quantifiers
            "a": 1,
            "an": 1,  # Handle "a week ago" or "an hour ago"
        }

        # Time unit multipliers (to convert to days)
        time_unit_multipliers = {
            "day": 1,
            "days": 1,
            "week": 7,
            "weeks": 7,
            "fortnight": 14,
            "month": 30,
            "months": 30,
            "quarter": 90,
            "year": 365,
            "years": 365,
        }

        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                groups = match.groups()

                # Different handling based on number of captured groups
                if len(groups) == 2:
                    # Standard pattern with number and unit
                    number_str = groups[0].lower()
                    unit_str = groups[1].lower()

                    # Handle special case for patterns with approximate quantifiers
                    if number_str in ["few", "couple", "several"]:
                        days_count = word_to_number.get(
                            number_str, 3
                        )  # Default to 3 if not found
                    elif number_str in word_to_number:
                        days_count = word_to_number[number_str]
                    else:
                        try:
                            days_count = int(number_str)
                        except ValueError:
                            # If we can't parse the number, default to 3
                            days_count = 3

                    # Apply the time unit multiplier
                    days = days_count * time_unit_multipliers.get(unit_str, 1)

                elif len(groups) == 1:
                    # Single unit pattern like "last week"
                    unit_str = groups[0].lower()
                    # Use default multiplier from the unit
                    days = time_unit_multipliers.get(unit_str, 7)  # Default to a week
                else:
                    # Something matched but not in expected format
                    continue

                # Calculate date range
                end_date = now.replace(hour=23, minute=59, second=59)
                start_date = (end_date - timedelta(days=days)).replace(
                    hour=0, minute=0, second=0
                )

                logger.info(
                    f"Found time pattern matching '{match.group(0)}'. Calculated {days} days from {start_date} to {end_date}"
                )

                return {
                    "is_past": True,
                    "days_range": days,
                    "reverse_chronological": True,
                    "specific_date": None,
                    "date_mentioned": True,
                    "time_mentioned": False,
                    "relative_reference": "past_days",
                    "date_range_start": start_date.strftime("%Y-%m-%d"),
                    "date_range_end": end_date.strftime("%Y-%m-%d"),
                    "query_match": match.group(
                        0
                    ),  # Store the actual matched text for debugging
                }

        # Additional pattern for "since yesterday", "since last week", etc.
        since_patterns = [
            r"(?i)since\s+(yesterday|today|last\s+week|last\s+month|last\s+year|a\s+week\s+ago|a\s+month\s+ago|a\s+year\s+ago)"
        ]

        for pattern in since_patterns:
            match = re.search(pattern, query)
            if match:
                time_ref = match.group(1).lower()

                # Calculate the reference date based on the matched phrase
                if "yesterday" in time_ref:
                    start_date = (now - timedelta(days=1)).replace(
                        hour=0, minute=0, second=0
                    )
                elif "today" in time_ref:
                    start_date = now.replace(hour=0, minute=0, second=0)
                elif "last week" in time_ref:
                    start_date = (now - timedelta(days=7)).replace(
                        hour=0, minute=0, second=0
                    )
                elif "last month" in time_ref:
                    start_date = (now - timedelta(days=30)).replace(
                        hour=0, minute=0, second=0
                    )
                elif "last year" in time_ref:
                    start_date = (now - timedelta(days=365)).replace(
                        hour=0, minute=0, second=0
                    )
                elif "week ago" in time_ref:
                    start_date = (now - timedelta(days=7)).replace(
                        hour=0, minute=0, second=0
                    )
                elif "month ago" in time_ref:
                    start_date = (now - timedelta(days=30)).replace(
                        hour=0, minute=0, second=0
                    )
                elif "year ago" in time_ref:
                    start_date = (now - timedelta(days=365)).replace(
                        hour=0, minute=0, second=0
                    )
                else:
                    # Default fallback
                    start_date = (now - timedelta(days=7)).replace(
                        hour=0, minute=0, second=0
                    )

                end_date = now.replace(hour=23, minute=59, second=59)
                days = (end_date - start_date).days

                logger.info(
                    f"Found 'since' pattern '{match.group(0)}'. Calculated {days} days from {start_date} to {end_date}"
                )

                return {
                    "is_past": True,
                    "days_range": days,
                    "reverse_chronological": True,
                    "specific_date": None,
                    "date_mentioned": True,
                    "time_mentioned": False,
                    "relative_reference": "since_date",
                    "date_range_start": start_date.strftime("%Y-%m-%d"),
                    "date_range_end": end_date.strftime("%Y-%m-%d"),
                    "query_match": match.group(0),
                }

        return None

    def _parse_with_llm(self, query: str, now: datetime) -> Optional[Dict[str, Any]]:
        """
        Use LLM to understand date references in natural language.

        Args:
            query: The user's query text
            now: Current datetime for reference

        Returns:
            Dictionary with parsed date information or None if parsing failed
        """
        if not self.llm_client:
            logger.info("LLM client not available for date parsing")
            return None

        try:
            # Create context from conversation history
            time_context = {
                "current_date": now.strftime("%Y-%m-%d"),
                "current_time": now.strftime("%H:%M:%S"),
                "last_mentioned_date": (
                    self.last_mentioned_date.strftime("%Y-%m-%d")
                    if self.last_mentioned_date
                    else None
                ),
                "conversation_references": (
                    [d.strftime("%Y-%m-%d") for d in self.conversation_references]
                    if self.conversation_references
                    else []
                ),
            }

            # Use the specialized date understanding method
            logger.info(
                f"Using specialized LLM date understanding for query: '{query}'"
            )
            result = self.llm_client.parse_date_understanding(query, time_context)

            if not result or "error" in result:
                logger.warning(
                    f"Date understanding failed: {result.get('error', 'Unknown error')}"
                )
                return None

            # Process date fields that might be in string format
            if "specific_date" in result and result["specific_date"]:
                if isinstance(result["specific_date"], str):
                    try:
                        result["specific_date"] = datetime.fromisoformat(
                            result["specific_date"].split("T")[0]
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse specific_date: {e}")
                        result["specific_date"] = None

            # Process date range fields
            for field in ["date_range_start", "date_range_end"]:
                if field in result and result[field]:
                    if isinstance(result[field], str):
                        try:
                            result[field] = datetime.fromisoformat(
                                result[field].split("T")[0]
                            )
                        except Exception as e:
                            logger.warning(f"Failed to parse {field}: {e}")
                            result[field] = None

            # Update conversation context if we found a date
            if result.get("specific_date"):
                self.update_conversation_context(result["specific_date"])
            elif result.get("date_range_end"):
                self.update_conversation_context(result["date_range_end"])

            logger.info(f"Successfully parsed date with LLM: {result}")
            return result

        except Exception as e:
            logger.error(f"Error using LLM for date parsing: {e}")
            return None

    def parse_with_context(self, query, reference_date=None):
        """Parse natural language datetime from query, using conversation context."""
        query_lower = query.lower()
        result = {
            "is_past": False,
            "days_range": 1,
            "reverse_chronological": False,
            "specific_date": None,
            "date_mentioned": False,
            "time_mentioned": False,
            "relative_reference": None,
            "date_range_start": None,
            "date_range_end": None,
        }

        # Use provided reference date or current time
        now = reference_date or datetime.now()
        logger.info(f"Starting date parsing for query: '{query_lower}'")
        logger.info(f"Current datetime: {now}")

        # First try LLM-based parsing
        llm_result = self._parse_with_llm(query, now)
        if llm_result:
            logger.info("Successfully parsed date with LLM")
            return llm_result

        # If LLM parsing fails, fall back to pattern-based approaches
        logger.info(
            "LLM parsing failed or unavailable, falling back to pattern matching"
        )

        # First check for "last N days" pattern
        last_n_days = self._parse_last_n_days_pattern(query_lower, now)
        if last_n_days:
            return last_n_days

        # Try to determine if the query is oriented towards past or future events
        is_past_oriented = any(
            term in query_lower
            for term in ["previous", "past", "last", "before", "earlier"]
        )
        is_future_oriented = any(
            term in query_lower
            for term in ["next", "upcoming", "future", "later", "coming"]
        )

        # Default to past if "show me" or "what are" is used without future indicators
        if (
            "show me" in query_lower or "what are" in query_lower
        ) and not is_future_oriented:
            is_past_oriented = True

        if is_past_oriented and not is_future_oriented:
            logger.info("Query orientation: past")
            result["is_past"] = True
            result["reverse_chronological"] = True
        else:
            logger.info("Query orientation: future")

        # First, try direct pattern matching for specific query formats
        # Direct pattern match for the exact query format
        exact_patterns = [
            r"(?i)show me events from (last|previous|this|next) (monday|tuesday|wednesday|thursday|friday|saturday|sunday) to (tomorrow|yesterday|today)",
            r"(?i)show me events from (today|tomorrow|yesterday) to (tomorrow|yesterday|today)",
            r"(?i)show me events from (last|previous|this|next) (monday|tuesday|wednesday|thursday|friday|saturday|sunday) to (last|previous|this|next) (monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        ]

        logger.info(f"Trying exact pattern match first for query: '{query_lower}'")
        for i, pattern in enumerate(exact_patterns):
            logger.info(f"Testing pattern {i}: {pattern}")
            match = re.search(pattern, query_lower)
            if match:
                logger.info(f"Found exact match with pattern {i}: {match.groups()}")

                # Initialize start and end dates
                start_date = None
                end_date = None

                # First pattern: "show me events from [relative] [weekday] to [simple]"
                if i == 0:
                    relative_start = match.group(1)
                    weekday_start = match.group(2)
                    simple_end = match.group(3)

                    start_date = self._parse_relative_weekday(
                        now, relative_start, weekday_start
                    )
                    end_date = self._parse_simple_relative_day(now, simple_end)

                    logger.info(
                        f"Pattern 0: Start={relative_start} {weekday_start}={start_date}, End={simple_end}={end_date}"
                    )

                # Second pattern: "show me events from [simple] to [simple]"
                elif i == 1:
                    simple_start = match.group(1)
                    simple_end = match.group(2)

                    start_date = self._parse_simple_relative_day(now, simple_start)
                    end_date = self._parse_simple_relative_day(now, simple_end)

                    logger.info(
                        f"Pattern 1: Start={simple_start}={start_date}, End={simple_end}={end_date}"
                    )

                # Third pattern: "show me events from [relative] [weekday] to [relative] [weekday]"
                elif i == 2:
                    relative_start = match.group(1)
                    weekday_start = match.group(2)
                    relative_end = match.group(3)
                    weekday_end = match.group(4)

                    start_date = self._parse_relative_weekday(
                        now, relative_start, weekday_start
                    )
                    end_date = self._parse_relative_weekday(
                        now, relative_end, weekday_end
                    )

                    logger.info(
                        f"Pattern 2: Start={relative_start} {weekday_start}={start_date}, End={relative_end} {weekday_end}={end_date}"
                    )

                # If we've successfully parsed both dates
                if start_date and end_date:
                    # Make sure start is before end
                    if start_date > end_date:
                        logger.warning(
                            f"Start date {start_date} is after end date {end_date}, swapping"
                        )
                        start_date, end_date = end_date, start_date

                    # Calculate the date range in days
                    delta = (end_date - start_date).days + 1  # inclusive range
                    result["days_range"] = max(1, delta)
                    result["specific_date"] = start_date
                    result["date_mentioned"] = True
                    result["is_past"] = end_date < now

                    # Add explicit date range fields
                    result["date_range_start"] = start_date
                    result["date_range_end"] = end_date

                    logger.info(
                        f"EXACT MATCH - Date range: {delta} days, from {start_date} to {end_date}"
                    )
                    logger.info(
                        f"Setting date_range_start={start_date}, date_range_end={end_date}"
                    )

                    # Update conversation context - use end date as reference
                    self.update_conversation_context(end_date)
                    return result

        # If exact patterns don't match, continue with the rest of the logic
        logger.info("No exact pattern match, continuing with standard parsing")

        # Try to extract a date using dateparser with context
        date_settings = {
            "PREFER_DATES_FROM": "past" if is_past_oriented else "future",
            "RELATIVE_BASE": self.last_mentioned_date or now,
            "STRICT_PARSING": False,
        }

        try:
            parsed_date = dateparser.parse(query, settings=date_settings)
            if parsed_date:
                logger.info(f"Dateparser parsed: {parsed_date} from query: {query}")
                result["specific_date"] = parsed_date
                result["date_mentioned"] = True
                result["days_range"] = 1  # Default for specific dates
                result["is_past"] = parsed_date < now

                # Update conversation context
                self.update_conversation_context(parsed_date)
                logger.info(f"Returning dateparser result: {result}")
                return result
        except Exception as e:
            logger.warning(f"Dateparser failed: {e}")

        logger.info("Dateparser didn't find a date, trying pattern-based approaches")

        # If dateparser fails, try more specific approaches
        logger.info("Dateparser didn't find a date, trying pattern-based approaches")

        # 1. Check for relative references to previous context
        relative_patterns = [
            r"(?:the )?day (?:before|after) that",
            r"(?:the )?following day",
            r"(?:the )?previous day",
            r"next one",
            r"(?:the )?day (?:before|after)",
            r"(?:the )?same day next week",
        ]

        for pattern in relative_patterns:
            if re.search(pattern, query_lower):
                if self.last_mentioned_date:
                    if "before" in pattern or "previous" in pattern:
                        result["specific_date"] = self.last_mentioned_date - timedelta(
                            days=1
                        )
                    elif (
                        "after" in pattern
                        or "following" in pattern
                        or "next" in pattern
                    ):
                        result["specific_date"] = self.last_mentioned_date + timedelta(
                            days=1
                        )
                    elif "same day next week" in pattern:
                        result["specific_date"] = self.last_mentioned_date + timedelta(
                            days=7
                        )

                    result["date_mentioned"] = True
                    result["days_range"] = 1
                    result["is_past"] = result["specific_date"] < now
                    result["relative_reference"] = pattern

                    # Update conversation context
                    self.update_conversation_context(result["specific_date"])
                    return result

        # 2. Check for common time expressions

        # Today/Yesterday/Tomorrow
        if "yesterday" in query_lower:
            result["specific_date"] = now - timedelta(days=1)
            result["date_mentioned"] = True
            result["days_range"] = 1
            result["is_past"] = True
            logger.info(f"Found 'yesterday' reference: {result['specific_date']}")
            self.update_conversation_context(result["specific_date"])
            return result

        elif "today" in query_lower or "tonight" in query_lower:
            result["specific_date"] = now
            result["date_mentioned"] = True
            result["days_range"] = 1
            logger.info(f"Found 'today' reference: {result['specific_date']}")
            self.update_conversation_context(result["specific_date"])
            return result

        elif "tomorrow" in query_lower:
            result["specific_date"] = now + timedelta(days=1)
            result["date_mentioned"] = True
            result["days_range"] = 1
            result["is_past"] = False
            logger.info(f"Found 'tomorrow' reference: {result['specific_date']}")
            self.update_conversation_context(result["specific_date"])
            return result

        # This/next/last week, month, year
        time_frame_patterns = [
            (r"this (day|week|month|year)", 0),
            (r"next (day|week|month|year)", 1),
            (r"last (day|week|month|year)", -1),
            (r"(\d+) (days?|weeks?|months?|years?) ago", -1),
            (r"in (\d+) (days?|weeks?|months?|years?)", 1),
        ]

        for pattern, direction in time_frame_patterns:
            match = re.search(pattern, query_lower)
            if match:
                if len(match.groups()) == 1:
                    # This/next/last patterns
                    unit = match.group(1)
                    if unit in self.time_frames:
                        days = self.time_frames[unit]

                        if direction == 0:  # this
                            result["days_range"] = days
                        elif direction > 0:  # next
                            result["days_range"] = days
                            result["is_past"] = False
                        else:  # last
                            result["days_range"] = days
                            result["is_past"] = True

                        return result
                elif len(match.groups()) == 2:
                    # X days/weeks/etc ago or in X days/weeks/etc
                    quantity = int(match.group(1))
                    unit = match.group(2).rstrip("s")  # Remove potential plural 's'

                    if unit in self.time_frames:
                        base_days = self.time_frames[unit]
                        days = quantity * base_days

                        if direction > 0:  # in X days/weeks
                            result["specific_date"] = now + timedelta(days=days)
                            result["is_past"] = False
                        else:  # X days/weeks ago
                            result["specific_date"] = now - timedelta(days=days)
                            result["is_past"] = True

                        result["date_mentioned"] = True
                        result["days_range"] = 1

                        # Update conversation context
                        self.update_conversation_context(result["specific_date"])
                        return result

        # 3. Check for date ranges with relative terms
        relative_date_ranges = [
            r"(?:from|between)?\s*(last|previous|this|next)\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*(?:to|through|until|and)\s*(today|tomorrow|yesterday|this|next|last)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)?",
            r"(?:from|between)?\s*(today|tomorrow|yesterday)\s*(?:to|through|until|and)\s*(today|tomorrow|yesterday|this|next|last)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)?",
            r"(?:from|between)?\s*(today|tomorrow|yesterday|this|next|last)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\s*(?:to|through|until|and)\s*(tomorrow|yesterday|today)",
        ]

        for pattern in relative_date_ranges:
            match = re.search(pattern, query_lower)
            if match:
                logger.info(f"Found relative date range pattern: {match.groups()}")

                # Initialize start and end dates
                start_date = None
                end_date = None

                # Parse start date
                if match.group(1) in ["last", "previous", "this", "next"]:
                    # Day of week pattern like "last Thursday"
                    relative = match.group(1)
                    weekday = match.group(2)
                    start_date = self._parse_relative_weekday(now, relative, weekday)
                    logger.info(f"Start date from '{relative} {weekday}': {start_date}")
                elif match.group(1) in ["today", "tomorrow", "yesterday"]:
                    # Simple relative day pattern
                    start_date = self._parse_simple_relative_day(now, match.group(1))
                    logger.info(f"Start date from '{match.group(1)}': {start_date}")

                # Parse end date
                if match.group(3) in [
                    "today",
                    "tomorrow",
                    "yesterday",
                ] and not match.group(4):
                    # Simple end relative day without weekday
                    end_date = self._parse_simple_relative_day(now, match.group(3))
                    logger.info(f"End date from '{match.group(3)}': {end_date}")
                elif match.group(3) in ["this", "next", "last"] and match.group(4):
                    # End day of week pattern like "next Sunday"
                    end_date = self._parse_relative_weekday(
                        now, match.group(3), match.group(4)
                    )
                    logger.info(
                        f"End date from '{match.group(3)} {match.group(4)}': {end_date}"
                    )
                elif match.group(3) is None and match.group(4) is not None:
                    # Implicit "this" for the weekday
                    end_date = self._parse_relative_weekday(now, "this", match.group(4))
                    logger.info(
                        f"End date from implicit 'this {match.group(4)}': {end_date}"
                    )

                # Handle the case where the start/end are in a different order
                if match.groups()[-1] in ["tomorrow", "yesterday", "today"]:
                    # End is a simple relative term like "tomorrow"
                    end_date = self._parse_simple_relative_day(now, match.groups()[-1])
                    logger.info(
                        f"End date from final group '{match.groups()[-1]}': {end_date}"
                    )

                # If we've successfully parsed both dates
                if start_date and end_date:
                    # Make sure start is before end
                    if start_date > end_date:
                        logger.warning(
                            f"Start date {start_date} is after end date {end_date}, swapping"
                        )
                        start_date, end_date = end_date, start_date

                    # Calculate the date range in days
                    delta = (end_date - start_date).days + 1  # inclusive range
                    result["days_range"] = max(1, delta)
                    result["specific_date"] = start_date
                    result["date_mentioned"] = True
                    result["is_past"] = end_date < now

                    # Add explicit date range fields
                    result["date_range_start"] = start_date
                    result["date_range_end"] = end_date

                    logger.info(
                        f"Relative date range: {delta} days, from {start_date} to {end_date}"
                    )

                    # Update conversation context - use end date as reference
                    self.update_conversation_context(end_date)
                    return result

        # Continue with other date range patterns
        range_patterns = [
            r"between (.+?) and (.+)",
            r"from (.+?) to (.+)",
            r"(.+?) through (.+)",
            r"(.+?) until (.+)",
            r"(.+?) to (.+)",
        ]

        for pattern in range_patterns:
            match = re.search(pattern, query_lower)
            if match:
                start_str, end_str = match.groups()
                logger.info(f"Found date range pattern: '{start_str}' to '{end_str}'")

                try:
                    start_date = dateparser.parse(start_str, settings=date_settings)
                    end_date = dateparser.parse(end_str, settings=date_settings)
                    logger.info(f"Range parsed: start={start_date}, end={end_date}")

                    if start_date and end_date:
                        # Calculate the date range in days
                        delta = (end_date - start_date).days
                        result["days_range"] = max(1, delta)
                        result["specific_date"] = start_date
                        result["date_mentioned"] = True
                        result["is_past"] = end_date < now

                        # Add explicit date range fields
                        result["date_range_start"] = start_date
                        result["date_range_end"] = end_date

                        logger.info(
                            f"Date range: {delta} days, starting from {start_date}"
                        )

                        # Update conversation context - use end date as reference
                        self.update_conversation_context(end_date)
                        logger.info(f"Returning date range result: {result}")
                        return result
                    else:
                        logger.warning(
                            f"Failed to parse one of the range dates: start={start_date}, end={end_date}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to parse date range: {e}")

        # Special handling for specific relative terms
        if "yesterday" in query_lower:
            result["specific_date"] = now - timedelta(days=1)
            result["date_mentioned"] = True
            result["days_range"] = 1
            result["is_past"] = True
            logger.info(f"Found 'yesterday' reference: {result['specific_date']}")
            self.update_conversation_context(result["specific_date"])
            return result

        elif "today" in query_lower or "tonight" in query_lower:
            result["specific_date"] = now
            result["date_mentioned"] = True
            result["days_range"] = 1
            logger.info(f"Found 'today' reference: {result['specific_date']}")
            self.update_conversation_context(result["specific_date"])
            return result

        elif "tomorrow" in query_lower:
            result["specific_date"] = now + timedelta(days=1)
            result["date_mentioned"] = True
            result["days_range"] = 1
            result["is_past"] = False
            logger.info(f"Found 'tomorrow' reference: {result['specific_date']}")
            self.update_conversation_context(result["specific_date"])
            return result

        # Process "weeks from now" or "days from now" patterns
        # Add more variations of the pattern to handle different phrasings
        weeks_from_now_patterns = [
            r"(\d+)\s+weeks?\s+from\s+now",
            r"(\d+)\s+weeks?\s+from\s+today",
            r"what (?:day|date) (?:will it be|is it|would it be) (\d+) weeks? from (?:now|today)",
            r"(\d+) weeks? from (?:now|today)",
        ]

        for pattern in weeks_from_now_patterns:
            weeks_match = re.search(pattern, query_lower)
            if weeks_match:
                weeks = int(weeks_match.group(1))
                result["specific_date"] = now + timedelta(weeks=weeks)
                result["date_mentioned"] = True
                result["days_range"] = 1
                result["is_past"] = False
                logger.info(f"Found '{weeks} weeks from now' pattern: {pattern}")
                logger.info(
                    f"Current date: {now}, Target date: {result['specific_date']}"
                )
                self.update_conversation_context(result["specific_date"])
                return result

        # Similar for days from now
        days_from_now_patterns = [
            r"(\d+)\s+days?\s+from\s+now",
            r"(\d+)\s+days?\s+from\s+today",
            r"what (?:day|date) (?:will it be|is it|would it be) (\d+) days? from (?:now|today)",
            r"(\d+) days? from (?:now|today)",
        ]

        for pattern in days_from_now_patterns:
            days_match = re.search(pattern, query_lower)
            if days_match:
                days = int(days_match.group(1))
                result["specific_date"] = now + timedelta(days=days)
                result["date_mentioned"] = True
                result["days_range"] = 1
                result["is_past"] = False
                logger.info(f"Found '{days} days from now' pattern: {pattern}")
                logger.info(
                    f"Current date: {now}, Target date: {result['specific_date']}"
                )
                self.update_conversation_context(result["specific_date"])
                return result

        # If we've made it here, fallback to rule-based time frame detection
        time_frame_indicators = [
            ("today", 1, 0),
            ("this week", 7, 0),
            ("next week", 7, 7),
            ("last week", 7, -7),
            ("this month", 30, 0),
            ("next month", 30, 30),
            ("last month", 30, -30),
            ("this year", 365, 0),
        ]

        for indicator, days, offset in time_frame_indicators:
            if indicator in query_lower:
                result["days_range"] = days
                if offset < 0:
                    result["is_past"] = True

                if offset != 0:
                    # Calculate specific reference date for "next week", "last month", etc.
                    reference_date = now + timedelta(days=offset)
                    result["specific_date"] = reference_date
                    result["date_mentioned"] = True

                return result

        # Finally, determine if request seems to be for past or future
        # based on general sentence analysis
        if is_past_oriented:
            result["is_past"] = True

        # Special handling for "recent" or "latest"
        if any(word in query_lower for word in ["recent", "latest", "last"]):
            result["reverse_chronological"] = True
            if result["is_past"]:
                result["days_range"] = (
                    30  # Look back a reasonable amount for recent items
                )

        # Add final logging
        logger.info(f"Final parsing result: {result}")
        return result

    # Helper methods for parsing relative dates
    def _parse_simple_relative_day(self, base_date, relative_term):
        """Parse simple relative terms like 'today', 'tomorrow', 'yesterday'"""
        if relative_term == "today":
            return base_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif relative_term == "tomorrow":
            return (base_date + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif relative_term == "yesterday":
            return (base_date - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        return None

    def _parse_relative_weekday(self, base_date, relative_term, weekday_name):
        """Parse relative weekday terms like 'last Monday', 'next Friday'"""
        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        if weekday_name not in weekday_map:
            return None

        target_weekday = weekday_map[weekday_name]
        current_weekday = base_date.weekday()

        # Calculate days difference to the target weekday
        if relative_term == "this":
            # This week's target day - might be in the past
            days_diff = target_weekday - current_weekday
            if days_diff < 0:  # Target day already passed this week
                days_diff += 7
        elif relative_term == "next":
            # Next week's target day
            days_diff = target_weekday - current_weekday
            if days_diff <= 0:  # Target day is today or already passed this week
                days_diff += 7
        elif relative_term in ["last", "previous"]:
            # Last week's target day
            days_diff = target_weekday - current_weekday
            if days_diff > 0:  # Target day is in the future this week
                days_diff -= 7

        # Calculate the date
        target_date = base_date + timedelta(days=days_diff)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0)


# Singleton instance for application-wide use
_smart_date_parser = None


def get_smart_date_parser():
    """Get or create the SmartDateParser singleton instance"""
    global _smart_date_parser
    if _smart_date_parser is None:
        _smart_date_parser = SmartDateParser()
    return _smart_date_parser
