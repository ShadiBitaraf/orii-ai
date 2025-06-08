"""
Enhanced Prompt Engineering for ORII Calendar Assistant
======================================================

This module implements the sophisticated 5-prompt strategy for natural language calendar queries.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of processing a calendar query"""

    intent: str
    response: str
    events: List[Dict[str, Any]]
    confidence: float
    needs_clarification: bool
    clarification_question: str = ""


class EnhancedCalendarProcessor:
    """Enhanced calendar query processor using the 5-prompt strategy"""

    def __init__(self, llm_client=None):
        """Initialize with LLM client"""
        self.logger = logging.getLogger(__name__)

        # Import calendar service here to handle import errors gracefully
        try:
            from ..core.calendar.calendar_service import (
                get_calendar_service,
                get_events,
                get_visible_calendars,
            )
            from ..core.calendar.event_retrieval import get_events_in_range
            from ..cli.calendar_id_helper import find_matching_calendars

            self.get_calendar_service = get_calendar_service
            self.get_events = get_events
            self.get_events_in_range = get_events_in_range
            self.get_visible_calendars = get_visible_calendars
            self.find_matching_calendars = find_matching_calendars
            self.calendar_available = True
            self.logger.info("Google Calendar API services loaded successfully")
        except ImportError as e:
            self.logger.warning(f"Google Calendar API not available: {e}")
            self.calendar_available = False
            self.get_calendar_service = None
            self.get_events = None
            self.get_events_in_range = None
            self.get_visible_calendars = None
            self.find_matching_calendars = None

        # Initialize LLM client
        if llm_client:
            self.llm_client = llm_client
        else:
            try:
                from ..utils.llm_client import get_llm_client

                self.llm_client = get_llm_client()
            except ImportError:
                self.logger.error("LLM client not available")
                self.llm_client = None

    def process_calendar_query(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> QueryResult:
        """Main processing function implementing the 5-prompt strategy"""
        self.logger.debug(f"Processing query: {user_query}")

        try:
            # Step 1: Classify intent
            intent_result = self.classify_intent(user_query, user_context)
            intent = intent_result.get("intent", "CLARIFICATION_NEEDED")
            confidence = intent_result.get("confidence", 0.0)
            time_direction = intent_result.get("time_direction", "present")
            is_followup = intent_result.get("is_followup", False)
            original_context = intent_result.get("original_context", "")

            self.logger.info(
                f"Intent classified as: {intent} (confidence: {confidence}, direction: {time_direction})"
            )

            # Add time_direction to user_context for downstream functions
            user_context["time_direction"] = time_direction

            # Step 2: Handle different intents
            if intent == "GENERAL_CHAT":
                response = self.handle_general_chat(user_query)
                return QueryResult(
                    intent=intent,
                    response=response,
                    events=[],
                    confidence=confidence,
                    needs_clarification=False,
                )

            elif intent == "CALENDAR_INFO":
                response = self.handle_calendar_info(user_query)
                return QueryResult(
                    intent=intent,
                    response=response,
                    events=[],
                    confidence=confidence,
                    needs_clarification=False,
                )

            elif intent == "CLARIFICATION_FOLLOWUP":
                # Handle follow-up responses
                return self._handle_followup_query(
                    user_query, user_context, original_context, confidence
                )

            elif intent == "FETCH_EVENTS_TIME":
                return self._handle_time_based_query(
                    user_query, user_context, confidence
                )

            elif intent == "FETCH_EVENTS_SEMANTIC":
                return self._handle_semantic_query(user_query, user_context, confidence)

            elif intent == "CLARIFICATION_NEEDED":
                clarification = self.request_clarification(
                    user_query, "ambiguous_query"
                )
                return QueryResult(
                    intent=intent,
                    response=clarification,
                    events=[],
                    confidence=confidence,
                    needs_clarification=True,
                    clarification_question=clarification,
                )

            else:
                # Default response for unknown intents
                response = "I'm not sure how to help with that. Could you rephrase your question?"
                return QueryResult(
                    intent="UNKNOWN",
                    response=response,
                    events=[],
                    confidence=0.0,
                    needs_clarification=True,
                )

        except Exception as e:
            self.logger.error(f"Error in process_calendar_query: {e}")
            error_response = (
                "I encountered an error processing your request. Please try again."
            )
            return QueryResult(
                intent="ERROR",
                response=error_response,
                events=[],
                confidence=0.0,
                needs_clarification=False,
            )

    def _handle_followup_query(
        self,
        user_query: str,
        user_context: Dict,
        original_context: str,
        confidence: float,
    ) -> QueryResult:
        """Handle follow-up queries that provide additional context"""
        # Reconstruct the original query with the new context
        enhanced_query = f"{original_context} {user_query}"

        # Re-classify the enhanced query to determine if it's time-based or semantic
        enhanced_context = user_context.copy()
        enhanced_context["enhanced_query"] = enhanced_query

        intent_result = self.classify_intent(enhanced_query, enhanced_context)
        new_intent = intent_result.get("intent", "FETCH_EVENTS_SEMANTIC")
        time_direction = intent_result.get(
            "time_direction", user_context.get("time_direction", "present")
        )

        # Update context with new time direction
        user_context["time_direction"] = time_direction

        self.logger.info(
            f"Follow-up query enhanced: '{enhanced_query}' -> {new_intent} ({time_direction})"
        )

        # Route to appropriate handler
        if new_intent == "FETCH_EVENTS_TIME":
            return self._handle_time_based_query(
                enhanced_query, user_context, confidence
            )
        else:
            return self._handle_semantic_query(enhanced_query, user_context, confidence)

    def _handle_time_based_query(
        self, user_query: str, user_context: Dict, confidence: float
    ) -> QueryResult:
        """Handle time-based calendar queries with smart filtering and incremental search"""
        # Step 1: Parse calendar specification
        calendar_spec = self._parse_calendar_specification(user_query, user_context)

        # Step 2: Get target calendars
        target_calendars = self._get_target_calendars(calendar_spec)
        if not target_calendars:
            return QueryResult(
                intent="ERROR",
                response="I couldn't access your calendars. Please check your calendar permissions.",
                events=[],
                confidence=0.0,
                needs_clarification=False,
            )

        # Step 3: Extract time parameters
        time_params = self.extract_time_parameters(user_query, user_context)

        if time_params["confidence"] < 0.7:
            clarification = self.request_clarification(user_query, "unclear_time")
            return QueryResult(
                intent="CLARIFICATION_NEEDED",
                response=clarification,
                events=[],
                confidence=confidence,
                needs_clarification=True,
                clarification_question=clarification,
            )

        # Step 4: Determine if we should use incremental search
        time_direction = user_context.get("time_direction", "present")
        use_incremental = self._should_use_incremental_search(
            user_query, time_direction
        )

        if use_incremental:
            # Use smart incremental search
            events = self._smart_incremental_search(
                user_query, time_direction, "time_based", target_calendars
            )
        else:
            # Use traditional time range fetch
            events = self._fetch_events_by_time_range(time_params, target_calendars)

        # Step 5: Handle no results case
        if not events and use_incremental:
            # Offer to search further if no results in 1 year
            time_period = "past year" if time_direction == "past" else "next year"
            extended_search_response = f"I couldn't find any matching events in the {time_period}. Here are your options:\n• Would you like me to search further back in time?\n• Can you provide more specific details about what you're looking for?\n• Try a different search term or date range?"

            return QueryResult(
                intent="CLARIFICATION_NEEDED",
                response=extended_search_response,
                events=[],
                confidence=confidence,
                needs_clarification=True,
                clarification_question=extended_search_response,
            )

        # Step 6: Generate conversational response
        response = self.generate_conversational_response(
            user_query, "FETCH_EVENTS_TIME", events, user_context
        )

        return QueryResult(
            intent="FETCH_EVENTS_TIME",
            response=response,
            events=events,
            confidence=confidence,
            needs_clarification=False,
        )

    def _handle_semantic_query(
        self, user_query: str, user_context: Dict, confidence: float
    ) -> QueryResult:
        """Handle semantic event matching queries with smart filtering and incremental search"""
        # Step 1: Parse calendar specification
        calendar_spec = self._parse_calendar_specification(user_query, user_context)

        # Step 2: Get target calendars
        target_calendars = self._get_target_calendars(calendar_spec)
        if not target_calendars:
            return QueryResult(
                intent="ERROR",
                response="I couldn't access your calendars. Please check your calendar permissions.",
                events=[],
                confidence=0.0,
                needs_clarification=False,
            )

        # Step 3: Determine time direction and search strategy
        time_direction = user_context.get("time_direction", "present")

        # For semantic queries, always use incremental search for efficiency
        events = self._smart_incremental_search(
            user_query, time_direction, "semantic", target_calendars
        )

        # Step 4: Handle no results case with extended search offer
        if not events:
            time_period = (
                "past year"
                if time_direction == "past"
                else "next year" if time_direction == "future" else "current period"
            )

            # Create helpful suggestions based on the query type
            suggestions = self._generate_search_suggestions(user_query)

            extended_search_response = f"I couldn't find any matching events in the {time_period}. Here are some suggestions:\n"
            for suggestion in suggestions:
                extended_search_response += f"• {suggestion}\n"

            extended_search_response += "\nWould you like me to search further back in time or try a different approach?"

            return QueryResult(
                intent="CLARIFICATION_NEEDED",
                response=extended_search_response,
                events=[],
                confidence=confidence,
                needs_clarification=True,
                clarification_question=extended_search_response,
            )

        # Step 5: Generate conversational response
        response = self.generate_conversational_response(
            user_query, "FETCH_EVENTS_SEMANTIC", events, user_context
        )

        return QueryResult(
            intent="FETCH_EVENTS_SEMANTIC",
            response=response,
            events=events,
            confidence=confidence,
            needs_clarification=False,
        )

    def _should_use_incremental_search(
        self, user_query: str, time_direction: str
    ) -> bool:
        """Determine if incremental search should be used based on query characteristics"""
        query_lower = user_query.lower()

        # Use incremental search for "last" or "next" queries
        incremental_indicators = [
            "last",
            "previous",
            "recent",
            "latest",
            "next",
            "upcoming",
            "future",
            "when is my next",
        ]

        return any(indicator in query_lower for indicator in incremental_indicators)

    def _fetch_events_by_time_range(
        self, time_params: Dict, target_calendars: List[Dict]
    ) -> List[Dict]:
        """Fetch events using traditional time range (for specific dates like 'today', 'tomorrow')"""
        if not self.calendar_available or not target_calendars:
            return []

        try:
            # Parse datetime strings
            start_datetime = datetime.fromisoformat(
                time_params["start_datetime"].replace("Z", "")
            )
            end_datetime = datetime.fromisoformat(
                time_params["end_datetime"].replace("Z", "")
            )

            # Get calendar service
            service = self.get_calendar_service()
            if not service:
                return []

            all_events = []
            for calendar in target_calendars:
                cal_id = calendar.get("id")
                cal_name = calendar.get("summary", "Unknown")

                try:
                    events = self.get_events(
                        service=service,
                        calendar_id=cal_id,
                        time_min=start_datetime.isoformat() + "Z",
                        time_max=end_datetime.isoformat() + "Z",
                        max_results=50,
                        single_events=True,
                        orderby="startTime",
                    )

                    # Add calendar info to events
                    for event in events:
                        event["calendarId"] = cal_id
                        event["calendarName"] = cal_name

                    all_events.extend(events)

                except Exception as e:
                    self.logger.error(f"Error fetching from calendar {cal_name}: {e}")
                    continue

            self.logger.info(
                f"Fetched {len(all_events)} events from {len(target_calendars)} calendars"
            )
            return all_events

        except Exception as e:
            self.logger.error(f"Error fetching events by time range: {e}")
            return []

    def _generate_search_suggestions(self, user_query: str) -> List[str]:
        """Generate helpful search suggestions based on the query"""
        query_lower = user_query.lower()
        suggestions = []

        if "therapy" in query_lower:
            suggestions.extend(
                [
                    "Check if it might be under 'counseling' or 'mental health'",
                    "Look for appointments with your therapist's name",
                    "Consider if it was scheduled in a different calendar",
                ]
            )
        elif "flight" in query_lower or "travel" in query_lower:
            suggestions.extend(
                [
                    "Check if it's saved under airline name or flight number",
                    "Look for 'trip' or 'vacation' events",
                    "Consider checking your email calendar imports",
                ]
            )
        elif "meeting" in query_lower:
            suggestions.extend(
                [
                    "Try searching by the person's name you're meeting with",
                    "Look for 'call' or 'conference' events",
                    "Check if it's in your work calendar specifically",
                ]
            )
        else:
            suggestions.extend(
                [
                    "Try using more specific keywords",
                    "Check if the event might be under a different name",
                    "Consider if it was scheduled in a different calendar",
                ]
            )

        return suggestions

    def classify_intent(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PROMPT 1: Intent Classification with conversation context"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )
        user_timezone = user_context.get("timezone", "UTC")

        # Include conversation history for context
        chat_history = user_context.get("chat_history", [])
        conversation_context = ""
        if len(chat_history) >= 2:  # At least one exchange
            last_assistant_msg = next(
                (
                    msg["content"]
                    for msg in reversed(chat_history)
                    if msg["role"] == "assistant"
                ),
                "",
            )
            last_user_msg = next(
                (
                    msg["content"]
                    for msg in reversed(chat_history[:-1])
                    if msg["role"] == "user"
                ),
                "",
            )
            if last_assistant_msg and last_user_msg:
                conversation_context = f"\nPrevious conversation context:\nUser: {last_user_msg}\nAssistant: {last_assistant_msg}\n"

        prompt = f"""You are ORII, an intelligent calendar assistant. Analyze the user's query and classify their intent.

Current date and time: {current_datetime}
User timezone: {user_timezone}
{conversation_context}
User query: "{user_query}"

Classify the intent into ONE of these categories:

1. GENERAL_CHAT - Non-calendar related questions (greetings, how are you, weather, etc.)
2. CALENDAR_INFO - Questions about calendar access, how the system works
3. FETCH_EVENTS_TIME - Time-based calendar queries (today, tomorrow, next week, etc.)
4. FETCH_EVENTS_SEMANTIC - Semantic event searches (therapy, dentist, meetings with person X, flights, travel)
5. CLARIFICATION_FOLLOWUP - Follow-up responses to previous clarification questions
6. CLARIFICATION_NEEDED - Query is too ambiguous to process

**IMPORTANT TIME DETECTION:**
- Words like "last", "previous", "when was" = look in PAST
- Words like "next", "upcoming", "when is" = look in FUTURE  
- Words like "today", "now" = look in PRESENT
- Single keywords after clarification questions = CLARIFICATION_FOLLOWUP

**Context Awareness:**
- If this appears to be a follow-up to a previous question, classify as CLARIFICATION_FOLLOWUP
- Consider conversation history when determining intent

Examples:
"Hi how are you?" → GENERAL_CHAT
"What calendars can you access?" → CALENDAR_INFO  
"What do I have tomorrow?" → FETCH_EVENTS_TIME
"When was my last therapy session?" → FETCH_EVENTS_SEMANTIC (PAST)
"When is my flight to SF?" → FETCH_EVENTS_SEMANTIC (FUTURE)
"therapy" (after asking about therapy) → CLARIFICATION_FOLLOWUP
"sfo" (after asking about flights) → CLARIFICATION_FOLLOWUP
"Show me meetings" → CLARIFICATION_NEEDED (missing time context)

Return JSON with this format:
{{
  "intent": "FETCH_EVENTS_SEMANTIC",
  "confidence": 0.95,
  "time_direction": "past|future|present",
  "is_followup": true|false,
  "original_context": "extracted context from conversation if followup"
}}"""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            result = json.loads(response)

            # Ensure required fields exist
            result.setdefault("intent", "CLARIFICATION_NEEDED")
            result.setdefault("confidence", 0.0)
            result.setdefault("time_direction", "present")
            result.setdefault("is_followup", False)
            result.setdefault("original_context", "")

            return result
        except (json.JSONDecodeError, Exception) as e:
            self.logger.error(f"Intent classification error: {e}")
            return {
                "intent": "CLARIFICATION_NEEDED",
                "confidence": 0.0,
                "time_direction": "present",
                "is_followup": False,
                "original_context": "",
            }

    def extract_time_parameters(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """PROMPT 2: Time Extraction with past/future awareness"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )
        user_timezone = user_context.get("timezone", "UTC")
        time_direction = user_context.get("time_direction", "present")

        prompt = f"""You are extracting time parameters from a calendar query.

User query: "{user_query}"
Current date and time: {current_datetime}
User timezone: {user_timezone}
Time direction hint: {time_direction}

Parse the temporal expressions and convert to specific date ranges:

**PRESENT/FUTURE Examples:**
- "today" → start: 2025-06-08 00:00:00, end: 2025-06-08 23:59:59
- "tomorrow" → start: 2025-06-09 00:00:00, end: 2025-06-09 23:59:59  
- "next week" → start: 2025-06-09 00:00:00, end: 2025-06-15 23:59:59
- "this weekend" → start: 2025-06-14 00:00:00, end: 2025-06-15 23:59:59
- "next Monday" → start: 2025-06-09 00:00:00, end: 2025-06-09 23:59:59

**PAST Examples (when time_direction is "past"):**
- "last week" → start: 2025-05-25 00:00:00, end: 2025-05-31 23:59:59
- "yesterday" → start: 2025-06-07 00:00:00, end: 2025-06-07 23:59:59
- "last month" → start: 2025-05-01 00:00:00, end: 2025-05-31 23:59:59
- "last therapy" → start: 2025-01-01 00:00:00, end: 2025-06-08 23:59:59 (last 6 months)
- "when was my last" → start: 2025-01-01 00:00:00, end: 2025-06-08 23:59:59 (extended past range)

**SEMANTIC QUERIES (no specific time):**
- For queries about "last X" or "when was" → use extended past range (6 months back)
- For queries about "next X" or "upcoming" → use extended future range (3 months forward)
- For general semantic queries → use wide range (6 months back + 3 months forward)

Return JSON:
{{
  "start_datetime": "2025-06-08T00:00:00",
  "end_datetime": "2025-06-08T23:59:59",
  "time_description": "today",
  "time_direction": "past|present|future",
  "confidence": 0.98
}}

If time cannot be parsed, set confidence to 0.0.
Return ONLY the JSON response."""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            result = json.loads(response)

            # Ensure required fields
            result.setdefault("time_direction", time_direction)
            result.setdefault("confidence", 0.0)

            return result
        except (json.JSONDecodeError, Exception) as e:
            self.logger.error(f"Time extraction error: {e}")

            # Provide default time range based on direction
            now = datetime.now()
            if time_direction == "past":
                start_time = now - timedelta(days=180)  # 6 months back
                end_time = now
            elif time_direction == "future":
                start_time = now
                end_time = now + timedelta(days=90)  # 3 months forward
            else:  # present or unknown
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_time = now.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            return {
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "time_description": f"default_{time_direction}_range",
                "time_direction": time_direction,
                "confidence": 0.5,
            }

    def semantic_event_matching(
        self, user_query: str, calendar_events: List[Dict], user_context: Dict
    ) -> Dict:
        """PROMPT 3: Semantic Event Matching"""

        user_timezone = user_context.get("timezone", "UTC")
        current_date = user_context.get("current_datetime", datetime.now().isoformat())
        events_json = json.dumps(calendar_events, indent=2, default=str)

        prompt = f"""You are analyzing calendar events to find semantic matches for a user query.

User query: "{user_query}"
User timezone: {user_timezone}
Current date: {current_date}

Here are the user's calendar events:
{events_json}

Your task:
1. Understand what TYPE of event the user is looking for semantically
2. Match events based on meaning, not just exact word matching
3. Consider synonyms, related terms, and context
4. Look at event titles, descriptions, attendees, and locations

Semantic matching guidelines:
- "therapy" matches: "Dr. Smith", "Mental health", "Counseling", "Therapist visit"
- "workout" matches: "Gym", "Yoga", "Fitness", "Personal training", "Exercise class"
- "dentist" matches: "Dr. Jones DDS", "Dental cleaning", "Teeth appointment"
- "dinner" matches: "Dinner with X", "Restaurant", "Meal with", "Eating out"
- "meeting with [person]" matches: events where that person is an attendee or mentioned

Return a JSON response:
{{
  "matches": [
    {{
      "event_id": "event_123",
      "title": "Event Title",
      "start_time": "2025-06-08T15:00:00",
      "confidence": 0.95,
      "match_reason": "Event title contains 'Dr. Smith' which semantically matches 'therapy session'"
    }}
  ],
  "total_matches": 1
}}

If no semantic matches found, return empty matches array.
Return ONLY the JSON response."""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Semantic matching error: {e}")
            return {"matches": [], "total_matches": 0}

    def generate_conversational_response(
        self,
        user_query: str,
        detected_intent: str,
        calendar_results: List[Dict],
        user_context: Dict,
    ) -> str:
        """PROMPT 4: Conversational Response Generation with bullet formatting"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )
        time_direction = user_context.get("time_direction", "present")

        # Format calendar results for better display
        if calendar_results:
            formatted_events = []
            for event in calendar_results:
                if isinstance(event, dict):
                    title = event.get("title", event.get("summary", "Untitled Event"))
                    start_time = event.get(
                        "start_time", event.get("start", {}).get("dateTime", "")
                    )
                    location = event.get("location", "")

                    # Format start time for display
                    try:
                        if start_time:
                            from datetime import datetime as dt

                            dt_obj = dt.fromisoformat(start_time.replace("Z", ""))
                            time_str = dt_obj.strftime("%I:%M %p on %B %d")
                        else:
                            time_str = "All day"
                    except:
                        time_str = str(start_time) if start_time else "Time TBD"

                    event_str = f"**{title}** - {time_str}"
                    if location:
                        event_str += f" ({location})"
                    formatted_events.append(event_str)

            results_text = "\n• " + "\n• ".join(formatted_events)
        else:
            results_text = "No events found"

        prompt = f"""You are ORII, a friendly and helpful calendar assistant. Generate a natural, conversational response to the user.

Context:
- User query: "{user_query}"
- Intent: {detected_intent}
- Time direction: {time_direction}
- Calendar results: {results_text}
- Current time: {current_datetime}

Response guidelines:
1. Be conversational and warm, not robotic
2. Use natural language, avoid technical jargon
3. **ALWAYS use bullet points (•) when listing multiple events or items**
4. If no events found, be helpful and suggest alternatives
5. For general chat, be friendly but redirect to calendar help
6. Present calendar information in an easy-to-read bullet format
7. For past queries, use past tense ("You had", "Your last")
8. For future queries, use future tense ("You have coming up", "Your next")

**Formatting Examples:**
✅ Good format:
"Here's what you have coming up tomorrow:
• **Meeting with John** - 2:00 PM (Conference Room A)
• **Dentist Appointment** - 4:30 PM (Dr. Smith's Office)

Would you like more details about any of these?"

✅ Good format for no results:
"I couldn't find any therapy sessions in your recent calendar. Here are some suggestions:
• Check if it might be under a different name (counseling, mental health, etc.)
• Look for appointments with specific doctor names
• Consider if it was scheduled in a different calendar

Would you like me to search for something more specific?"

❌ Bad format:
"Query processed. 2 events retrieved for specified timeframe."

❌ Bad format:
"No semantic matches found in database."

For empty results, always offer helpful suggestions in bullet points.
For single events, still use a bullet point for consistency.

Generate a helpful, natural response based on the context provided.
Return ONLY the response text, no JSON or markup."""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return response.strip()
        except Exception as e:
            self.logger.error(f"Response generation error: {e}")
            if calendar_results:
                # Fallback formatting if LLM fails
                event_count = len(calendar_results)
                if event_count == 1:
                    return f"I found 1 event for you:\n• {calendar_results[0].get('title', 'Event')}"
                else:
                    return f"I found {event_count} events for you. Let me know if you'd like more details!"
            else:
                return "I couldn't find any matching events in your calendar. Could you provide more details or try a different search term?"

    def request_clarification(self, user_query: str, ambiguity_reason: str) -> str:
        """PROMPT 5: Clarification Request"""

        prompt = f"""The user's query is ambiguous and needs clarification.

User query: "{user_query}"
Issue identified: {ambiguity_reason}

Generate a friendly clarification question that helps the user be more specific.

Common clarification scenarios:
- Missing time context: "When would you like me to check?" 
- Vague event type: "What kind of meeting are you looking for?"
- Multiple possible interpretations: "Are you looking for X or Y?"

Examples:
Query: "Show me meetings" 
Clarification: "I'd be happy to show you your meetings! What time period are you interested in - today, this week, or something else?"

Query: "When did I meet John?"
Clarification: "I can help you find when you met with John! Are you looking for a specific John, or would you like me to search for all meetings with people named John?"

Generate a natural, helpful clarification question.
Return ONLY the clarification question, no JSON or markup."""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return response.strip()
        except Exception as e:
            logger.error(f"Clarification generation error: {e}")
            return (
                "Could you please provide more details about what you're looking for?"
            )

    def handle_general_chat(self, user_query: str) -> str:
        """Handle general chat queries with predefined responses"""
        query_lower = user_query.lower()

        if any(word in query_lower for word in ["hi", "hello", "hey"]):
            return "Hi there! I'm doing great, thanks for asking. How can I help you with your calendar today?"
        elif any(word in query_lower for word in ["how are you", "how're you"]):
            return "I'm doing well! I'm here to help you manage your calendar. What would you like to know about your schedule?"
        elif "weather" in query_lower:
            return "I don't have access to weather information, but I can help you with your calendar! Is there anything on your schedule you'd like to know about?"
        else:
            return "I'm here to help you with your calendar! You can ask me about your upcoming events, schedule meetings, or search for past appointments."

    def handle_calendar_info(self, user_query: str) -> str:
        """Handle questions about calendar system capabilities"""
        return """I'm ORII, your AI calendar assistant! I can help you with:

• **View your schedule** - "What do I have today?" or "Show me next week"
• **Find specific events** - "When was my last dentist appointment?"
• **Search by people** - "When did I last meet with John?"
• **Semantic search** - "Show me my workout sessions" or "Find my therapy appointments"

I have access to your Google Calendar and can understand natural language queries. Just ask me anything about your schedule!"""

    def _parse_calendar_specification(
        self, user_query: str, user_context: Dict
    ) -> Dict[str, Any]:
        """Parse if user specified a particular calendar to search"""
        query_lower = user_query.lower()

        # Look for calendar specifications
        calendar_indicators = [
            "in my",
            "from my",
            "on my",
            "check my",
            "look in",
            "search in",
            "from",
            "in",
            "on",
            "calendar",
            "cal",
        ]

        # Check if user specified a particular calendar
        specified_calendar = None

        # Common calendar names to look for
        calendar_patterns = [
            "work",
            "personal",
            "home",
            "family",
            "school",
            "business",
            "primary",
            "main",
            "default",
            "uci",
            "handshake",
            "canvas",
        ]

        for pattern in calendar_patterns:
            if pattern in query_lower:
                # Found a potential calendar specification
                specified_calendar = pattern
                self.logger.info(f"User specified calendar: {specified_calendar}")
                break

        return {
            "specified_calendar": specified_calendar,
            "use_all_visible": specified_calendar is None,
        }

    def _get_target_calendars(self, calendar_spec: Dict[str, Any]) -> List[Dict]:
        """Get the target calendars to query based on user specification"""
        if not self.calendar_available:
            return []

        try:
            service = self.get_calendar_service()
            if not service:
                return []

            if calendar_spec["specified_calendar"]:
                # User specified a particular calendar
                matching_calendars = self.find_matching_calendars(
                    service, calendar_spec["specified_calendar"]
                )
                if matching_calendars:
                    cal_names = [
                        cal.get("summary", "Unknown") for cal in matching_calendars
                    ]
                    self.logger.info(f"Found specified calendars: {cal_names}")
                    return matching_calendars
                else:
                    self.logger.warning(
                        f"No calendar found matching '{calendar_spec['specified_calendar']}', using visible calendars"
                    )

            # Use all visible calendars (default behavior)
            visible_calendars = self.get_visible_calendars()
            cal_names = [cal.get("summary", "Unknown") for cal in visible_calendars]
            self.logger.info(
                f"Using {len(visible_calendars)} visible calendars: {cal_names}"
            )
            return visible_calendars

        except Exception as e:
            self.logger.error(f"Error getting target calendars: {e}")
            return []

    def _smart_incremental_search(
        self,
        user_query: str,
        time_direction: str,
        search_type: str,
        target_calendars: List[Dict],
    ) -> List[Dict]:
        """Perform smart month-by-month search until events found or 1 year reached"""
        if not self.calendar_available or not target_calendars:
            return []

        try:
            service = self.get_calendar_service()
            if not service:
                return []

            now = datetime.now()
            found_events = []
            months_searched = 0
            max_months = 12  # Search up to 1 year

            self.logger.info(
                f"Starting incremental search: {search_type} in {time_direction} direction"
            )

            while months_searched < max_months and not found_events:
                if time_direction == "past":
                    # Search backwards month by month
                    end_date = now - timedelta(days=30 * months_searched)
                    start_date = now - timedelta(days=30 * (months_searched + 1))
                elif time_direction == "future":
                    # Search forwards month by month
                    start_date = now + timedelta(days=30 * months_searched)
                    end_date = now + timedelta(days=30 * (months_searched + 1))
                else:
                    # Present - just search current month
                    start_date = now.replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0
                    )
                    end_date = now.replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    )

                month_name = start_date.strftime("%B %Y")
                self.logger.info(f"Searching month {months_searched + 1}: {month_name}")

                # Search each target calendar for this month
                month_events = []
                for calendar in target_calendars:
                    cal_id = calendar.get("id")
                    cal_name = calendar.get("summary", "Unknown")

                    try:
                        events = self.get_events(
                            service=service,
                            calendar_id=cal_id,
                            time_min=start_date.isoformat() + "Z",
                            time_max=end_date.isoformat() + "Z",
                            max_results=50,
                            single_events=True,
                            orderby="startTime",
                        )

                        # Add calendar info to events
                        for event in events:
                            event["calendarId"] = cal_id
                            event["calendarName"] = cal_name

                        month_events.extend(events)

                    except Exception as e:
                        self.logger.error(f"Error searching calendar {cal_name}: {e}")
                        continue

                if month_events:
                    # Apply semantic filtering if this is a semantic search
                    if search_type == "semantic":
                        semantic_matches = self.semantic_event_matching(
                            user_query,
                            month_events,
                            {"current_datetime": now.isoformat(), "timezone": "UTC"},
                        )
                        filtered_events = semantic_matches.get("matches", [])
                    else:
                        filtered_events = month_events

                    if filtered_events:
                        found_events = filtered_events
                        self.logger.info(
                            f"Found {len(found_events)} events in {month_name}"
                        )
                        break

                months_searched += 1

                # Break if we're searching present (only current month)
                if time_direction == "present":
                    break

            if not found_events and months_searched >= max_months:
                self.logger.info(
                    f"No events found after searching {months_searched} months"
                )

            return found_events

        except Exception as e:
            self.logger.error(f"Error in incremental search: {e}")
            return []


# Test function for the 15 query categories
def test_enhanced_prompts():
    """Test the enhanced prompt strategy with 15 query categories"""

    test_queries = [
        # Category 1: General/Unrelated Queries
        "Hi, how are you today?",
        "What calendars do you have access to?",
        "How does this assistant work?",
        "What's the weather like?",
        # Category 2: Basic Time-Based Fetching
        "What do I have today?",
        "What's on my schedule tomorrow?",
        "Show me next week's meetings",
        "What do I have this weekend?",
        "Any appointments next Monday?",
        # Category 3: Semantic Event Matching
        "When was my last therapy session?",
        "When is my next gathering with friends?",
        "When did I last meet with john@company.com?",
        "Show me my dental appointments",
        "When is my next workout?",
        # Category 4: Complex Contextual Queries
        "What meetings do I have with my manager this week?",
    ]

    try:
        processor = EnhancedCalendarProcessor()
        user_context = {
            "current_datetime": datetime.now().isoformat(),
            "timezone": "America/New_York",
        }

        results = []
        for query in test_queries:
            try:
                result = processor.process_calendar_query(query, user_context)
                results.append(
                    {
                        "query": query,
                        "intent": result.intent,
                        "confidence": result.confidence,
                        "response": (
                            result.response[:100] + "..."
                            if len(result.response) > 100
                            else result.response
                        ),
                        "needs_clarification": result.needs_clarification,
                    }
                )
            except Exception as e:
                results.append({"query": query, "error": str(e)})

        return results
    except Exception as e:
        return [{"error": f"Setup failed: {e}"}]


if __name__ == "__main__":
    results = test_enhanced_prompts()
    for result in results:
        print(json.dumps(result, indent=2))
