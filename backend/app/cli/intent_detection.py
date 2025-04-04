"""
Intent detection and query processing functions for the CLI.
"""

import re
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from .time_manager import parse_time_range
import os
import json

from ..utils.smart_date_parser import get_smart_date_parser
from ..utils.llm_client import get_llm_client

# Import the LLM model - using a placeholder, replace with actual implementation
try:
    from ..utils.llm_client import get_llm_client
except ImportError:
    # Define a fallback for development/testing
    def get_llm_client():
        """Fallback function when LLM client isn't available"""
        return None


def determine_query_intent(query: str) -> Dict[str, Any]:
    """
    Determine the intent of a query using LLM-powered understanding.

    Args:
        query: The natural language query

    Returns:
        Dictionary containing the intent type, confidence level, and other parameters
    """
    print(f"[DEBUG] Processing query intent: '{query}'")

    # Get LLM client
    llm_client = get_llm_client()
    if not llm_client:
        print("[DEBUG] LLM client not available, using fallback methods")
        # Continue with fallback methods...

    # First, extract temporal information using SmartDateParser
    parser = get_smart_date_parser()
    time_info = parser.parse_with_context(query)
    print(f"[DEBUG] Time info from parser: {time_info}")

    # Determine intent using LLM
    print("[DEBUG] Using LLM for intent classification")

    try:
        # Use the LLM to classify the intent with the time information
        intent_data = llm_client.classify_intent(query, time_info)
        print(f"[DEBUG] Parsed intent data: {intent_data}")

        # Detect last/next occurrence intent
        query_lower = query.lower()

        # Check for last/previous event queries if not explicitly set by LLM
        if "is_find_last_occurrence" not in intent_data:
            last_occurrence_phrases = [
                "when was the last",
                "when was my last",
                "most recent",
                "find the last",
                "last time",
            ]
            intent_data["is_find_last_occurrence"] = any(
                phrase in query_lower for phrase in last_occurrence_phrases
            )

            if intent_data["is_find_last_occurrence"]:
                print(f"[DEBUG] Detected 'find last occurrence' type query: {query}")
                # For these queries, we want to search backwards in time
                intent_data["is_past"] = True
                intent_data["reverse_chronological"] = True
                # Use a much larger time window for searching
                if (
                    not intent_data.get("days_range")
                    or intent_data.get("days_range", 0) < 30
                ):
                    intent_data["days_range"] = 365
                    print(
                        f"[DEBUG] Expanded search window to {intent_data['days_range']} days for 'last occurrence' query"
                    )

        # Check for next/upcoming event queries if not explicitly set by LLM
        if "is_find_next_occurrence" not in intent_data:
            next_occurrence_phrases = [
                "when is my next",
                "when is the next",
                "when is",
                "when will",
                "upcoming",
                "scheduled",
            ]
            intent_data["is_find_next_occurrence"] = any(
                phrase in query_lower for phrase in next_occurrence_phrases
            )

            if intent_data["is_find_next_occurrence"]:
                print(f"[DEBUG] Detected 'find next occurrence' type query: {query}")
                # For these queries, we want to search forward in time
                intent_data["is_past"] = False
                intent_data["reverse_chronological"] = False
                # Use a much larger time window for searching
                if (
                    not intent_data.get("days_range")
                    or intent_data.get("days_range", 0) < 30
                ):
                    intent_data["days_range"] = 365
                    print(
                        f"[DEBUG] Expanded search window to {intent_data['days_range']} days for 'next occurrence' query"
                    )

        # Make sure we transfer any relevant time_info to the intent_data
        # if it's not already present
        for key in [
            "specific_date",
            "date_range_start",
            "date_range_end",
            "is_past",
            "days_range",
            "reverse_chronological",
        ]:
            if (
                key in time_info
                and time_info[key] is not None
                and key not in intent_data
            ):
                print(
                    f"[DEBUG] Adding {key} from time_info to intent_data: {time_info[key]}"
                )
                intent_data[key] = time_info[key]
            elif key in time_info and time_info[key] is not None and key in intent_data:
                # Prefer the parser's temporal information over LLM's
                print(
                    f"[DEBUG] Overriding {key} in intent_data with time_info: {intent_data[key]} -> {time_info[key]}"
                )
                intent_data[key] = time_info[key]

        return intent_data

    except Exception as e:
        print(f"[DEBUG] Error with LLM intent classification: {e}")
        print("[DEBUG] Falling back to rule-based approach")

    # If we reach here, LLM classification failed
    # Simple rule-based fallback
    query_lower = query.lower()
    result = {
        "intent_type": "calendar_query",  # Default intent
        "is_past": time_info.get("is_past", False),
        "days_range": time_info.get("days_range", 7),
        "reverse_chronological": time_info.get("reverse_chronological", False),
        "specific_date": time_info.get("specific_date"),
        "date_range_start": time_info.get("date_range_start"),
        "date_range_end": time_info.get("date_range_end"),
    }

    # Determine intent type based on keywords
    if "create" in query_lower or "schedule" in query_lower or "add" in query_lower:
        result["intent_type"] = "event_creation"
    elif (
        "what time" in query_lower
        or "what day" in query_lower
        or "what date" in query_lower
    ):
        result["intent_type"] = "time_date"
    elif any(
        term in query_lower
        for term in ["show", "list", "display", "get", "find", "when", "what"]
    ):
        result["intent_type"] = "calendar_query"

    print(f"[DEBUG] Rule-based intent result: {result}")
    return result


def classify_intent_with_llm(
    query: str, time_info: Dict[str, Any], llm_client
) -> Dict[str, Any]:
    """
    Use LLM to classify the intent of a query

    Args:
        query: The user's natural language query
        time_info: Extracted time information
        llm_client: Client for LLM API

    Returns:
        Dictionary containing intent information
    """
    # Enhanced prompt template for intent classification with better date context
    prompt = f"""
    Analyze the following calendar assistant query and determine the user's intent.
    Query: "{query}"
    
    The system has already performed date/time parsing and extracted the following temporal information:
    {json.dumps(time_info, default=str)}
    
    Consider the context carefully in your classification. Pay special attention to:
    - Whether the query is asking about a specific date
    - Whether that date is in the past or future
    - If the query is asking about the current date/time
    - If it's asking for a range of dates or a specific day
    - If it's asking about which calendars the assistant has access to
    - If the user is specifying a particular calendar to search (e.g., "in my work calendar", "on my personal calendar")
    - If the user is asking to see/list all available calendars
    - If the query is about finding free time slots, empty time, or checking availability
    - If the query is asking about when the user has time for an activity of a specific duration
    - If the query is asking about the "least busy day" or when they're most free
    
    Very important: If the query is asking which calendars are available, accessible, or visible to the system, 
    like "what calendars do you have access to", "show me my calendars", or "list my calendars", this should be 
    classified as "calendar_access_query".
    
    Return your analysis as a JSON object with the following fields:
    - intent_type: One of ["calendar_query", "event_creation", "time_date", "greeting", "assistant_info", "calendar_list", "calendar_access_query", "availability_analysis"]
    - is_past: Boolean, whether the query refers to past events
    - days_range: Integer, the number of days to look back/forward
    - needs_calendar_data: Boolean, whether calendar data needs to be fetched
    - is_creation: Boolean, whether the user wants to create an event
    - reverse_chronological: Boolean, whether results should be shown in reverse chronological order
    - search_terms: List of relevant search terms for filtering events, or null if not applicable
    - specified_calendar: String containing the name of the calendar if the user specified one (e.g., "work", "personal", "family"), or null if not specified
    - calendar_access_query: Boolean, true if the user is asking which calendars are available or visible
    - availability_query: Boolean, true if the user is asking about free time, availability, or when they can schedule something
    - availability_duration_minutes: Integer, duration in minutes for availability query (if applicable), or null
    
    If the query is explicitly asking about the current date or time (e.g., "what day is it today"), make sure to classify it as "time_date" intent.
    
    If the query is asking about which calendars the assistant can see, access, or has permission to, ALWAYS classify it as "calendar_access_query" intent and set calendar_access_query to true, never as "assistant_info".
    
    If the query is about free time, availability, finding empty slots, or when the user has time for something, classify it as "availability_analysis" and set availability_query to true.

    If the user mentions a specific calendar to search in (e.g., "check my work calendar", "events in my family calendar"), extract the calendar name (like "work" or "family") and include it in the specified_calendar field.
    """

    print(f"[DEBUG] Sending prompt to LLM: {prompt[:200]}...")

    try:
        # Call the LLM to classify intent (explicitly using gpt-4 model)
        response = llm_client.get_completion(prompt, model="gpt-4")
        print(f"[DEBUG] LLM response: {response[:200]}...")

        intent_data = json.loads(response)
        print(f"[DEBUG] Parsed intent data: {intent_data}")

        # Validate and ensure all required fields are present
        required_fields = [
            "intent_type",
            "is_past",
            "days_range",
            "needs_calendar_data",
            "is_creation",
            "reverse_chronological",
            "specified_calendar",
            "calendar_access_query",
        ]

        for field in required_fields:
            if field not in intent_data:
                # Set defaults for missing fields
                if field == "intent_type":
                    intent_data[field] = "calendar_query"
                elif field in [
                    "is_past",
                    "needs_calendar_data",
                    "is_creation",
                    "reverse_chronological",
                    "calendar_access_query",
                ]:
                    intent_data[field] = False
                elif field == "days_range":
                    intent_data[field] = 7
                elif field == "specified_calendar":
                    intent_data[field] = None
                print(
                    f"[DEBUG] Setting default for missing field {field}: {intent_data[field]}"
                )

        # Make sure to properly handle date_mentioned information from time_info
        if time_info.get("date_mentioned") and time_info.get("specific_date"):
            # Override with specific date info if available
            intent_data["specific_date"] = time_info["specific_date"]
            print(
                f"[DEBUG] Setting specific_date from time_info: {intent_data['specific_date']}"
            )

            # If the query is asking about a date but there are no calendar indicators,
            # it might be a simple date query (e.g., "what date was yesterday")
            if (
                "what" in query.lower()
                and "date" in query.lower()
                and not intent_data["needs_calendar_data"]
            ):
                intent_data["intent_type"] = "time_date"
                print(f"[DEBUG] Overriding intent to time_date based on query pattern")

        # If calendar_access_query is true, ensure the intent_type is correct
        if intent_data.get("calendar_access_query"):
            intent_data["intent_type"] = "calendar_access_query"
            print(
                "[DEBUG] Setting intent_type to calendar_access_query based on calendar_access_query flag"
            )

        # Override with time_info values if they exist
        for key in time_info:
            if key in [
                "is_past",
                "days_range",
                "reverse_chronological",
                "specific_date",
            ]:
                old_value = intent_data.get(key)
                intent_data[key] = time_info[key]
                print(
                    f"[DEBUG] Overriding {key} from time_info: {old_value} -> {intent_data[key]}"
                )

        return intent_data

    except Exception as e:
        # Log the error
        print(f"[ERROR] Error using LLM for intent classification: {e}")
        # Fall back to rule-based approach
        return classify_intent_with_rules(query, time_info)


def classify_intent_with_rules(query: str, time_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback rule-based approach for intent classification

    Args:
        query: The user's natural language query
        time_info: Extracted time information

    Returns:
        Dictionary containing intent information
    """
    print("[DEBUG] Using rule-based intent classification")
    query_lower = query.lower()

    # Start with default values
    result = {
        "intent_type": "calendar_query",  # Default intent
        "is_past": time_info.get("is_past", False),
        "days_range": time_info.get("days_range", 7),
        "reverse_chronological": time_info.get("reverse_chronological", False),
        "specific_date": time_info.get("specific_date"),
        "date_range_start": time_info.get("date_range_start"),
        "date_range_end": time_info.get("date_range_end"),
        "specified_calendar": None,
        "calendar_access_query": False,
        "is_find_last_occurrence": False,
        "is_find_next_occurrence": False,
    }

    # Check for calendar access query
    calendar_access_patterns = [
        r"which\s+calendars?\s+(?:do\s+you|can\s+you|are\s+you|you)\s+(?:have|use|access|search|query|find|see)",
        r"what\s+calendars?\s+(?:do\s+you|can\s+you|are\s+you|you)\s+(?:have|use|access|search|query|find|see)",
        r"show\s+(?:me|)\s+(?:my|the|)\s+calendars?",
        r"list\s+(?:my|the|)\s+calendars?",
    ]

    for pattern in calendar_access_patterns:
        if re.search(pattern, query_lower, re.IGNORECASE):
            print(f"[DEBUG] Rule-based detection: calendar access query")
            result["intent_type"] = "calendar_access_query"
            result["calendar_access_query"] = True
            break

    # Check for specified calendar
    if not result["calendar_access_query"]:
        calendar_patterns = [
            r"in\s+(?:my|the)\s+(.+?)\s+calendar",
            r"from\s+(?:my|the)\s+(.+?)\s+calendar",
            r"on\s+(?:my|the)\s+(.+?)\s+calendar",
            r"check\s+(?:my|the)\s+(.+?)\s+calendar",
        ]

        for pattern in calendar_patterns:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                calendar_name = match.group(1).strip()
                print(
                    f"[DEBUG] Rule-based detection: specified calendar '{calendar_name}'"
                )
                result["specified_calendar"] = calendar_name
                break

    # Check for last/previous event queries
    last_occurrence_phrases = [
        "when was the last",
        "when was my last",
        "most recent",
        "find the last",
        "last time",
    ]
    if any(phrase in query_lower for phrase in last_occurrence_phrases):
        print(f"[DEBUG] Rule-based detection: 'find last occurrence' type query")
        result["is_find_last_occurrence"] = True
        result["is_past"] = True
        result["reverse_chronological"] = True
        if not result.get("days_range") or result.get("days_range") < 30:
            result["days_range"] = 365

    # Check for next/upcoming event queries
    next_occurrence_phrases = [
        "when is my next",
        "when is the next",
        "when is",
        "when will",
        "upcoming",
        "scheduled",
    ]
    if any(phrase in query_lower for phrase in next_occurrence_phrases):
        print(f"[DEBUG] Rule-based detection: 'find next occurrence' type query")
        result["is_find_next_occurrence"] = True
        result["is_past"] = False
        result["reverse_chronological"] = False
        if not result.get("days_range") or result.get("days_range") < 30:
            result["days_range"] = 365

    # Determine intent type based on keywords
    if not result[
        "calendar_access_query"
    ]:  # Skip if we already determined it's a calendar access query
        if "create" in query_lower or "schedule" in query_lower or "add" in query_lower:
            result["intent_type"] = "event_creation"
        elif (
            "what time" in query_lower
            or "what day" in query_lower
            or "what date" in query_lower
        ):
            result["intent_type"] = "time_date"
        elif any(
            term in query_lower
            for term in ["show", "list", "display", "get", "find", "when", "what"]
        ):
            result["intent_type"] = "calendar_query"

    print(f"[DEBUG] Rule-based intent result: {result}")
    return result


def extract_search_terms(query: str) -> Optional[List[str]]:
    """
    Extract search terms from a query to filter events by

    This function uses a more semantic approach that could be replaced by
    entity extraction with an LLM in the future.

    Args:
        query: Query string

    Returns:
        List of search terms or None
    """
    # Handle empty query
    if not query:
        return None

    # Normalize query
    query_lower = query.lower()

    # Load stopwords
    try:
        with open(os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r") as f:
            stopwords = set([line.strip() for line in f])
    except Exception as e:
        print(f"[ERROR] Error loading stopwords: {e}")
        stopwords = set()  # Fallback to empty set

    # Add some additional question-specific stopwords
    question_stopwords = set(
        [
            "when",
            "where",
            "what",
            "who",
            "why",
            "how",
            "which",
            "do",
            "does",
            "did",
            "is",
            "are",
            "was",
            "were",
            "have",
            "has",
            "had",
            "can",
            "could",
            "will",
            "would",
            "should",
            "may",
            "might",
            "must",
            "about",
            "at",
            "by",
            "for",
            "from",
            "next",
            "last",
            "previous",
            "upcoming",
            "recent",
            "find",
            "tell",
            "me",
            "my",
            "show",
            "get",
            "see",
            "check",
            "calendar",
            "event",
            "events",
        ]
    )
    stopwords.update(question_stopwords)

    # Process possessive patterns first - these are high-value signals
    # Pattern: [Name]'s [Event] - e.g., "Daria's graduation", "mom's birthday"
    possessive_pattern = re.search(r"\b(\w+)\'s\s+(\w+(?:\s+\w+){0,2})\b", query_lower)
    if possessive_pattern:
        person = possessive_pattern.group(1)
        event = possessive_pattern.group(2)

        # Only use the possessive if the person and event aren't stopwords
        if person not in stopwords and not any(
            word in stopwords for word in event.split()
        ):
            full_phrase = f"{person}'s {event}"
            print(f"[DEBUG] Extracted possessive phrase: '{full_phrase}'")

            # Use expanded search terms for the event type to improve matching
            try:
                from .event_management import get_expanded_search_terms

                expanded_terms = get_expanded_search_terms(full_phrase)
                print(f"[DEBUG] Expanded search terms: {expanded_terms}")
                return expanded_terms
            except ImportError:
                return [full_phrase]

    # Extract all words from the query
    words = re.findall(r"\b\w+\b", query_lower)

    # Find question indicator words
    question_indicators = ["when", "where", "what", "who", "how"]

    # Identify the question part
    question_end_idx = -1
    for idx, word in enumerate(words):
        if word in question_indicators:
            question_end_idx = idx
            # Look ahead for phrases like "when is my" or "where is the"
            for i in range(idx + 1, min(idx + 3, len(words))):
                if words[i] in [
                    "is",
                    "are",
                    "was",
                    "were",
                    "will",
                    "my",
                    "the",
                    "a",
                    "an",
                ]:
                    question_end_idx = i
                else:
                    break

    # Get all words after the question part
    if question_end_idx >= 0 and question_end_idx < len(words) - 1:
        content_words = words[question_end_idx + 1 :]
    else:
        content_words = words

    # Filter out stopwords
    content_words = [
        word for word in content_words if word not in stopwords and len(word) > 2
    ]

    if not content_words:
        print(f"[DEBUG] No meaningful content words found after filtering")
        return None

    # Build useful phrases from the content words
    # Start with the longest possible phrases
    phrases = []

    # 1. Try to find consecutive content words to form phrases
    current_phrase = []
    for word in content_words:
        current_phrase.append(word)

    if current_phrase:
        phrase = " ".join(current_phrase)
        phrases.append(phrase)
        print(f"[DEBUG] Extracted content phrase: '{phrase}'")

    # 2. If we have multiple content words, also add individual words as backup
    if len(content_words) > 1:
        # Add individual words that are likely important (longer words)
        for word in content_words:
            if len(word) > 3 and word not in phrases:
                phrases.append(word)
                print(f"[DEBUG] Added individual word: '{word}'")

    # 3. Look for specific patterns like "next [event]", "upcoming [event]"
    timeframe_indicators = ["next", "upcoming", "last", "previous", "recent"]
    for idx, word in enumerate(words):
        if word in timeframe_indicators and idx < len(words) - 1:
            next_word = words[idx + 1]
            if next_word not in stopwords and len(next_word) > 2:
                phrase = f"{word} {next_word}"
                if phrase not in phrases:
                    phrases.append(phrase)
                    print(f"[DEBUG] Added timeframe phrase: '{phrase}'")

    if not phrases:
        print(f"[DEBUG] No phrases extracted")
        return None

    # Expand each phrase with potential synonyms to improve matching
    expanded_phrases = []
    try:
        from .event_management import get_expanded_search_terms

        for phrase in phrases:
            expansions = get_expanded_search_terms(phrase)
            expanded_phrases.extend(expansions)
        print(f"[DEBUG] Expanded search phrases: {expanded_phrases}")
        return expanded_phrases
    except ImportError:
        print(f"[DEBUG] Final extracted search terms: {phrases}")
        return phrases
