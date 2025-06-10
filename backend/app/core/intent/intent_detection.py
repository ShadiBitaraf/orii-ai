"""
Intent detection and query processing functions for the CLI.
"""

import re
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from ..time.time_manager import parse_time_range
import os
import json
import logging
import time
import traceback

from ...utils.smart_date_parser import get_smart_date_parser
from ...utils.llm_client import get_llm_client

# Use only the real LLM client, no mock fallback
from ...utils.llm_client import get_llm_client

logger = logging.getLogger(__name__)


def determine_query_intent(
    query: str, conversation_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Determine the intent of a user query using a hybrid approach:
    1. LLM-powered intent classification for understanding
    2. Rule-based processing for execution

    Args:
        query: User's query string
        conversation_context: Optional conversation context

    Returns:
        Dict with intent type and parameters
    """
    logger.debug(f"Determining intent for query: {query}")

    # Step 1: Use LLM to understand the true intent
    llm_intent = classify_query_intent_with_llm(query, conversation_context)

    # Step 2: Use rule-based processing to extract time/search info
    rule_based_result = rule_based_intent_detection(query)

    # Step 3: Combine LLM understanding with rule-based extraction
    result = rule_based_result.copy()  # Start with rule-based data

    # Override intent type based on LLM classification
    intent_mapping = {
        "follow_up_question": "follow_up_question",
        "schedule_query": "search_events",
        "event_search": "search_events",
        "availability_check": "availability_check",
        "event_creation": "create_event",
        "non_calendar": "greeting",
        "time_date_query": "time_date",
    }

    llm_intent_type = llm_intent.get("intent", "schedule_query")
    mapped_intent = intent_mapping.get(llm_intent_type, "search_events")

    # Update result with LLM insights
    result.update(
        {
            "intent_type": mapped_intent,
            "llm_classification": llm_intent,
            "is_follow_up": llm_intent.get("is_follow_up", False),
            "question_type": llm_intent.get("question_type", "none"),
            "requested_detail": llm_intent.get("requested_detail", "none"),
            "confidence": llm_intent.get("confidence", 0.5),
        }
    )

    # Special handling for follow-up questions
    if mapped_intent == "follow_up_question":
        result["needs_calendar_data"] = True
        # For follow-ups, use a broader search range to find relevant events
        result["days_range"] = 30  # Look in a month range for context

    logger.debug(f"Final intent result: {result}")
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

    logger.debug(f"Sending prompt to LLM: {prompt[:200]}...")

    try:
        # Call the LLM to classify intent (explicitly using gpt-4 model)
        response = llm_client.get_completion(prompt, model="gpt-4")
        logger.debug(f"LLM response: {response[:200]}...")

        intent_data = json.loads(response)
        logger.debug(f"Parsed intent data: {intent_data}")

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
                logger.debug(
                    f"Setting default for missing field {field}: {intent_data[field]}"
                )

        # Make sure to properly handle date_mentioned information from time_info
        if time_info.get("date_mentioned") and time_info.get("specific_date"):
            # Override with specific date info if available
            intent_data["specific_date"] = time_info["specific_date"]
            logger.debug(
                f"Setting specific_date from time_info: {intent_data['specific_date']}"
            )

            # If the query is asking about a date but there are no calendar indicators,
            # it might be a simple date query (e.g., "what date was yesterday")
            if (
                "what" in query.lower()
                and "date" in query.lower()
                and not intent_data["needs_calendar_data"]
            ):
                intent_data["intent_type"] = "time_date"
                logger.debug(f"Overriding intent to time_date based on query pattern")

        # Extract search terms
        if "search_terms" not in intent_data or not intent_data["search_terms"]:
            intent_data["search_terms"] = extract_search_terms(query, time_info)

        # If calendar_access_query is true, ensure the intent_type is correct
        if intent_data.get("calendar_access_query"):
            intent_data["intent_type"] = "calendar_access_query"
            logger.debug(
                "Setting intent_type to calendar_access_query based on calendar_access_query flag"
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
                logger.debug(
                    f"Overriding {key} from time_info: {old_value} -> {intent_data[key]}"
                )

        return intent_data

    except Exception as e:
        # Log the error
        logger.error(f"Error using LLM for intent classification: {e}")
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
    logger.debug("Using rule-based intent classification")
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
        "search_terms": extract_search_terms(
            query, time_info
        ),  # Pass time_info to extract_search_terms
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
            logger.debug("Rule-based detection: calendar access query")
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
                logger.debug(
                    f"Rule-based detection: specified calendar '{calendar_name}'"
                )
                result["specified_calendar"] = calendar_name
                break

    # Check for last/previous event queries with stronger pattern matching
    # This will catch phrases like "when was my last therapy session"
    if re.search(r"when\s+(?:was|is)\s+(?:my|the)\s+last", query_lower) or (
        "last" in query_lower
        and any(
            term in query_lower
            for term in ["meeting", "call", "appointment", "event", "session"]
        )
    ):
        logger.debug("Rule-based detection: 'find last occurrence' type query")
        result["is_find_last_occurrence"] = True
        result["is_past"] = True
        result["reverse_chronological"] = True
        # Use a much larger time range for these queries - a full year
        result["days_range"] = 365

    # Check for next/upcoming event queries with stronger pattern matching
    if re.search(r"when\s+(?:is|will\s+be)\s+(?:my|the)\s+next", query_lower) or (
        "next" in query_lower
        and any(
            term in query_lower
            for term in ["meeting", "call", "appointment", "event", "session"]
        )
    ):
        logger.debug("Rule-based detection: 'find next occurrence' type query")
        result["is_find_next_occurrence"] = True
        result["is_past"] = False
        result["reverse_chronological"] = False
        # Use a much larger time range for these queries - a full year
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

    logger.debug(f"Rule-based intent result: {result}")
    return result


def extract_search_terms(
    query: str, time_info: Optional[Dict[str, Any]] = None
) -> Optional[List[str]]:
    """
    Extract search terms from a query to filter events by

    This function uses a more semantic approach that could be replaced by
    entity extraction with an LLM in the future.

    Args:
        query: Query string
        time_info: Time information parsed from the query

    Returns:
        List of search terms or None
    """
    # Handle empty query
    if not query:
        return None

    # Normalize query
    query_lower = query.lower()

    # If we have date info, don't include the parsed date pattern in search terms
    if time_info and time_info.get("parsed_from_pattern"):
        # Remove the detected date pattern from the query before extracting search terms
        date_pattern = time_info.get("parsed_from_pattern", "").lower()
        if date_pattern:
            # Replace the date pattern with empty space to avoid breaking phrases
            query_lower = query_lower.replace(date_pattern, " ")
            logger.debug(
                f"Removed date pattern '{date_pattern}' from query for search term extraction"
            )

    # Load stopwords
    try:
        with open(os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r") as f:
            stopwords = set([line.strip() for line in f])
    except Exception as e:
        logger.error(f"Error loading stopwords: {e}")
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
            "on",
            "in",
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
            logger.debug(f"Extracted possessive phrase: '{full_phrase}'")

            # Use expanded search terms for the event type to improve matching
            try:
                from ..calendar.event_management import get_expanded_search_terms

                expanded_terms = get_expanded_search_terms(full_phrase)
                logger.debug(f"Expanded search terms: {expanded_terms}")
                return expanded_terms
            except ImportError:
                return [full_phrase]

    # Filter out time-related words that shouldn't be search terms
    time_related_stopwords = {
        "coming",
        "upcoming",
        "next",
        "last",
        "previous",
        "past",
        "future",
        "ahead",
        "back",
        "forward",
        "backward",
        "recent",
        "today",
        "tomorrow",
        "yesterday",
        "week",
        "month",
        "year",
        "day",
        "time",
        "schedule",
        "calendar",
        "events",
        "event",
        "have",
        "having",
        "scheduled",
    }

    # Combine with existing stopwords
    all_stopwords = stopwords.union(time_related_stopwords)

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
    meaningful_words = [
        word for word in content_words if word not in all_stopwords and len(word) > 2
    ]

    if not meaningful_words:
        logger.debug(
            f"No meaningful content words found after filtering time-related words"
        )
        return None

    # Build useful phrases from the content words
    # Start with the longest possible phrases
    phrases = []

    # 1. Try to find consecutive meaningful words to form phrases
    current_phrase = []
    for word in meaningful_words:
        current_phrase.append(word)

    if current_phrase:
        phrase = " ".join(current_phrase)
        phrases.append(phrase)
        logger.debug(f"Extracted content phrase: '{phrase}'")

    # 2. If we have multiple meaningful words, also add individual words as backup
    if len(meaningful_words) > 1:
        # Add individual words that are likely important (longer words)
        for word in meaningful_words:
            if len(word) > 3 and word not in phrases:
                phrases.append(word)
                logger.debug(f"Added individual word: '{word}'")

    # 3. Look for specific patterns like "next [event]", "upcoming [event]"
    timeframe_indicators = ["next", "upcoming", "last", "previous", "recent"]
    for idx, word in enumerate(words):
        if word in timeframe_indicators and idx < len(words) - 1:
            next_word = words[idx + 1]
            if next_word not in stopwords and len(next_word) > 2:
                phrase = f"{word} {next_word}"
                if phrase not in phrases:
                    phrases.append(phrase)
                    logger.debug(f"Added timeframe phrase: '{phrase}'")

    if not phrases:
        logger.debug(f"No phrases extracted")
        return None

    # Expand each phrase with potential synonyms to improve matching
    expanded_phrases = []
    try:
        from ..calendar.event_management import get_expanded_search_terms

        for phrase in phrases:
            expansions = get_expanded_search_terms(phrase)
            expanded_phrases.extend(expansions)
        logger.debug(f"Expanded search phrases: {expanded_phrases}")
        return expanded_phrases
    except ImportError:
        logger.debug(f"Final extracted search terms: {phrases}")
        return phrases


def rule_based_intent_detection(query: str) -> Dict[str, Any]:
    """
    Use rule-based approach to determine query intent.

    Args:
        query: User's query string

    Returns:
        Dict with intent type and parameters
    """
    # Extract time information using pattern matching
    from ..time.time_manager import parse_time_range

    time_info = parse_time_range(query)

    # Extract search terms
    search_terms = extract_search_terms(query, time_info)

    # Check if this is a "last occurrence" or "next occurrence" query
    is_find_last_occurrence = False
    is_find_next_occurrence = False

    # Check for "when was the last..." or "when was my last..." patterns
    if re.search(r"when\s+(?:was|is)\s+(?:my|the)\s+last", query.lower()):
        is_find_last_occurrence = True
        time_info["is_past"] = True
        time_info["days_range"] = 365  # Look back an entire year

    # Check for "when is the next..." or "when is my next..." patterns
    if re.search(r"when\s+(?:is|will\s+be)\s+(?:my|the)\s+next", query.lower()):
        is_find_next_occurrence = True
        time_info["is_past"] = False
        time_info["days_range"] = 365  # Look ahead an entire year

    # Create basic intent data
    result = {
        "intent_type": "search_events",  # Default intent
        "is_past": time_info.get("is_past", False),
        "days_range": time_info.get("days_range", 7),
        "reverse_chronological": time_info.get("reverse_chronological", False),
        "specific_date": time_info.get("specific_date"),
        "date_range_start": time_info.get("date_range_start"),
        "date_range_end": time_info.get("date_range_end"),
        "search_terms": search_terms,
        "specified_calendar": None,
        "needs_calendar_data": True,
        "time_info": time_info,
        "is_find_last_occurrence": is_find_last_occurrence,
        "is_find_next_occurrence": is_find_next_occurrence,
    }

    # Check for greeting intents
    greeting_patterns = [
        r"^(?:hi|hello|hey|greetings|howdy|good morning|good afternoon|good evening)(?:\s|$)",
        r"^how are you",
    ]
    for pattern in greeting_patterns:
        if re.search(pattern, query.lower(), re.IGNORECASE):
            result["intent_type"] = "greeting"
            result["needs_calendar_data"] = False
            break

    # Return the result
    return result


def classify_query_intent_with_llm(
    query: str, conversation_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Use LLM to understand the true intent of the user's query, especially for follow-ups and complex questions.

    Args:
        query: User's query string
        conversation_context: Recent conversation history

    Returns:
        Dict with detailed intent classification
    """
    try:
        from ...utils.llm_client import get_llm_client

        llm_client = get_llm_client()

        # Get recent conversation context for follow-up detection
        recent_context = ""
        if conversation_context and conversation_context.get("chat_history"):
            recent_messages = conversation_context.get("chat_history", [])[
                -4:
            ]  # Last 4 messages
            context_parts = []
            for msg in recent_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role and content:
                    context_parts.append(f"{role.title()}: {content}")
            recent_context = "\n".join(context_parts)

        prompt = f"""Analyze this user query and classify its intent. Consider the recent conversation context.

Recent Conversation:
{recent_context if recent_context else "No recent context"}

Current Query: "{query}"

Classify the intent into ONE of these categories:

1. **follow_up_question** - User is asking a specific question about something mentioned in recent conversation
   - Examples: "is there a zoom link?", "what time is that?", "where is it located?"
   - Look for: yes/no questions, detail requests about recent events/meetings

2. **schedule_query** - User wants to see their calendar/schedule 
   - Examples: "what do I have tomorrow?", "show me my schedule", "what's coming up?"

3. **event_search** - User is searching for specific events
   - Examples: "when is my dentist appointment?", "find my meeting with John"

4. **availability_check** - User wants to know if they're free
   - Examples: "am I free on Friday?", "do I have anything at 3pm?"

5. **event_creation** - User wants to create/schedule something
   - Examples: "schedule a meeting", "add an event", "book lunch tomorrow"

6. **non_calendar** - Not related to calendar
   - Examples: "hello", "how are you?", "what's the weather?"

7. **time_date_query** - Asking about current time/date
   - Examples: "what time is it?", "what day is today?"

Respond with ONLY a JSON object:
{{
    "intent": "follow_up_question|schedule_query|event_search|availability_check|event_creation|non_calendar|time_date_query",
    "confidence": 0.0-1.0,
    "is_follow_up": true/false,
    "question_type": "yes_no|specific_detail|open_ended|none",
    "requested_detail": "zoom_link|location|time|date|description|none",
    "reasoning": "brief explanation"
}}"""

        result = llm_client.get_completion(prompt)

        # Parse the JSON response
        import json

        try:
            intent_data = json.loads(result)
            logger.debug(f"LLM intent classification: {intent_data}")
            return intent_data
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {result}")
            return {
                "intent": "schedule_query",
                "confidence": 0.5,
                "is_follow_up": False,
            }

    except Exception as e:
        logger.error(f"Error in LLM intent classification: {e}")
        return {"intent": "schedule_query", "confidence": 0.5, "is_follow_up": False}
