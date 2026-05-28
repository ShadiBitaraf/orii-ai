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

    def parse_with_context(self, query: str) -> Dict[str, Any]:
        """
        Parse a query with context from the LLM to extract date information.

        Args:
            query: The user query string

        Returns:
            Dict containing extracted date information
        """
        logger.info(f"Starting date parsing for query: '{query}'")
        logger.info(f"Current datetime: {datetime.now()}")

        # Check if we can use pattern matching for common date phrases
        pattern_result = self._check_common_patterns(query)
        if pattern_result:
            logger.info(f"Found date match using pattern matching: {pattern_result}")
            return pattern_result

        # Use the LLM for more complex date understanding
        logger.info(f"Using specialized LLM date understanding for query: '{query}'")

        time_info = {}

        try:
            # Get date understanding from LLM
            if self.llm_client:
                time_info = self.llm_client.parse_date_understanding(query)
                logger.info(f"Successfully parsed date with LLM: {time_info}")
            else:
                # Fallback to basic extraction if LLM not available
                time_info = self._extract_basic_date_info(query)
                logger.info(f"Using basic date extraction: {time_info}")
        except Exception as e:
            logger.error(f"Error parsing date with LLM: {e}")
            # Fallback to basic extraction
            time_info = self._extract_basic_date_info(query)
            logger.info(f"Falling back to basic date extraction: {time_info}")

        logger.info("Successfully parsed date with LLM")
        return time_info

    def _check_common_patterns(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Check for common date patterns in the query

        Args:
            query: The user query

        Returns:
            Date information dict if pattern found, None otherwise
        """
        query_lower = query.lower()
        now = datetime.now()

        # Check for specific month/day mentions
        month_day_pattern = r"(?:on|for|at)?\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}"

        month_match = re.search(month_day_pattern, query, re.IGNORECASE)
        if month_match:
            date_str = month_match.group(0).strip()
            # Remove leading "on", "for", etc.
            date_str = re.sub(r"^(?:on|for|at)\s+", "", date_str, flags=re.IGNORECASE)

            try:
                # Try to parse the date string - include the current year
                # since most queries don't specify the year
                parsed_date = date_parser.parse(f"{date_str}, {now.year}")

                # Adjust for past dates if query indicates past tense
                if "did" in query_lower or "was" in query_lower or "had" in query_lower:
                    is_past = True
                else:
                    is_past = False

                # If the date is in the past but the user didn't use past tense,
                # assume they meant next year's date
                if not is_past and parsed_date < now:
                    parsed_date = parsed_date.replace(year=now.year + 1)

                return {
                    "is_past": is_past,
                    "days_range": 1,
                    "reverse_chronological": False,
                    "specific_date": parsed_date,
                    "date_range_start": None,
                    "date_range_end": None,
                    "date_mentioned": True,
                    "parsed_from_pattern": date_str,
                }
            except:
                pass

        # Check for "today", "tomorrow", "yesterday"
        if "today" in query_lower:
            return {
                "is_past": False,
                "days_range": 1,
                "reverse_chronological": False,
                "specific_date": now.replace(hour=0, minute=0, second=0, microsecond=0),
                "date_range_start": None,
                "date_range_end": None,
                "date_mentioned": True,
            }
        elif "tomorrow" in query_lower:
            tomorrow = now + timedelta(days=1)
            return {
                "is_past": False,
                "days_range": 1,
                "reverse_chronological": False,
                "specific_date": tomorrow.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ),
                "date_range_start": None,
                "date_range_end": None,
                "date_mentioned": True,
            }
        elif "yesterday" in query_lower:
            yesterday = now - timedelta(days=1)
            return {
                "is_past": True,
                "days_range": 1,
                "reverse_chronological": False,
                "specific_date": yesterday.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ),
                "date_range_start": None,
                "date_range_end": None,
                "date_mentioned": True,
            }

        return None

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
