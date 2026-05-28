# all prompt strings (from enhanced_prompts.py)
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

            elif intent == "CREATE_EVENT":
                return self._handle_create_event_query(
                    user_query, user_context, confidence
                )

            elif intent == "UPDATE_EVENT":
                return self._handle_update_event_query(
                    user_query, user_context, confidence
                )

            elif intent == "DELETE_EVENT":
                return self._handle_delete_event_query(
                    user_query, user_context, confidence
                )

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
        """Handle follow-up queries that provide additional context with improved context awareness"""

        # **ENHANCED CONTEXT ANALYSIS** - Check if this is asking for details about previous results
        chat_history = user_context.get("chat_history", [])
        query_lower = user_query.lower()

        # Look for detail-seeking patterns
        detail_patterns = [
            "details",
            "more info",
            "tell me more",
            "what about",
            "about the",
            "grad prep",
            "therapy",
            "meeting",
            "appointment",
            "event",
        ]

        # Check if user is asking for details about something mentioned in recent conversation
        if len(chat_history) >= 2:
            last_assistant_response = ""
            for msg in reversed(chat_history):
                if msg["role"] == "assistant":
                    last_assistant_response = msg["content"].lower()
                    break

            # If the last response mentioned events and user is asking for details
            if any(pattern in query_lower for pattern in detail_patterns):
                # Check if the query term was mentioned in the last response
                query_terms = user_query.lower().split()
                for term in query_terms:
                    if len(term) > 3 and term in last_assistant_response:
                        # This looks like a detail request about a previously found event
                        clarification = f"I see you're asking about '{user_query}' which was mentioned in our previous conversation. Could you be more specific about what details you'd like to know? For example:\n"
                        clarification += "• What time is it scheduled?\n"
                        clarification += "• Where is it located?\n"
                        clarification += "• Who else is attending?\n"
                        clarification += "• Any other specific details?"

                        return QueryResult(
                            intent="CLARIFICATION_NEEDED",
                            response=clarification,
                            events=[],
                            confidence=confidence,
                            needs_clarification=True,
                            clarification_question=clarification,
                        )

        # **ORIGINAL LOGIC** - Reconstruct the original query with the new context
        enhanced_query = f"{original_context} {user_query}"

        # Re-classify the enhanced query to determine if it's time-based or semantic
        enhanced_context = user_context.copy()
        enhanced_context["enhanced_query"] = enhanced_query

        intent_result = self.classify_intent(enhanced_query, enhanced_context)
        new_intent = intent_result.get("intent", "FETCH_EVENTS_SEMANTIC")
        time_direction = intent_result.get("time_direction", "present")

        # Update context with new time direction
        enhanced_context["time_direction"] = time_direction

        # Process based on the new intent
        if new_intent == "FETCH_EVENTS_TIME":
            return self._handle_time_based_query(
                enhanced_query, enhanced_context, confidence
            )
        elif new_intent == "FETCH_EVENTS_SEMANTIC":
            return self._handle_semantic_query(
                enhanced_query, enhanced_context, confidence
            )
        else:
            # For other intents, provide a clarification
            clarification = self.request_clarification(
                enhanced_query, "followup_unclear"
            )
            return QueryResult(
                intent="CLARIFICATION_NEEDED",
                response=clarification,
                events=[],
                confidence=confidence,
                needs_clarification=True,
                clarification_question=clarification,
            )

    def _handle_create_event_query(
        self, user_query: str, user_context: Dict, confidence: float
    ) -> QueryResult:
        """Handle CREATE_EVENT intent with comprehensive event creation"""
        self.logger.info(f"Processing CREATE_EVENT: {user_query}")

        try:
            # Extract detailed event information using LLM
            event_details = self._extract_comprehensive_event_details(
                user_query, user_context
            )

            if event_details.get("needs_clarification", False):
                return QueryResult(
                    intent="CREATE_EVENT",
                    response=event_details.get(
                        "clarification_question",
                        "Could you provide more details about the event?",
                    ),
                    events=[],
                    confidence=confidence,
                    needs_clarification=True,
                    clarification_question=event_details.get(
                        "clarification_question", ""
                    ),
                )

            # Validate required fields
            if not event_details.get("summary"):
                return QueryResult(
                    intent="CREATE_EVENT",
                    response="I need at least an event title to create the event. What would you like to call it?",
                    events=[],
                    confidence=confidence,
                    needs_clarification=True,
                    clarification_question="What would you like to call the event?",
                )

            if not event_details.get("start_datetime"):
                return QueryResult(
                    intent="CREATE_EVENT",
                    response="When would you like to schedule this event?",
                    events=[],
                    confidence=confidence,
                    needs_clarification=True,
                    clarification_question="When would you like to schedule this event?",
                )

            # Create the event
            if self.calendar_available:
                try:
                    service = self.get_calendar_service()

                    # Resolve calendar name to calendar ID
                    calendar_name = event_details.get("calendar_name", "primary")
                    calendar_id = self._resolve_calendar_name_to_id(
                        service, calendar_name
                    )

                    # Import the create_event function
                    from ..core.calendar.event_management import create_event

                    created_event = create_event(
                        service, event_details, calendar_id=calendar_id
                    )

                    # Generate conversational response
                    response = self._generate_event_creation_response(
                        created_event, user_query
                    )

                    return QueryResult(
                        intent="CREATE_EVENT",
                        response=response,
                        events=[created_event],
                        confidence=confidence,
                        needs_clarification=False,
                    )

                except Exception as e:
                    self.logger.error(f"Error creating event: {e}")
                    return QueryResult(
                        intent="CREATE_EVENT",
                        response=f"I encountered an error creating the event: {str(e)}. Please try again.",
                        events=[],
                        confidence=confidence,
                        needs_clarification=False,
                    )
            else:
                return QueryResult(
                    intent="CREATE_EVENT",
                    response="Calendar service is not available. Please check your Google Calendar connection.",
                    events=[],
                    confidence=confidence,
                    needs_clarification=False,
                )

        except Exception as e:
            self.logger.error(f"Error in _handle_create_event_query: {e}")
            return QueryResult(
                intent="CREATE_EVENT",
                response="I encountered an error processing your request. Please try again with more details.",
                events=[],
                confidence=0.0,
                needs_clarification=False,
            )

    def _handle_update_event_query(
        self, user_query: str, user_context: Dict, confidence: float
    ) -> QueryResult:
        """Handle UPDATE_EVENT intent"""
        # TODO: Implement update event functionality for future iterations
        return QueryResult(
            intent="UPDATE_EVENT",
            response="Event updating functionality is coming soon! For now, you can delete the old event and create a new one.",
            events=[],
            confidence=confidence,
            needs_clarification=False,
        )

    def _handle_delete_event_query(
        self, user_query: str, user_context: Dict, confidence: float
    ) -> QueryResult:
        """Handle DELETE_EVENT intent"""
        # TODO: Implement delete event functionality for future iterations
        return QueryResult(
            intent="DELETE_EVENT",
            response="Event deletion functionality is coming soon! You can manually delete events from your Google Calendar for now.",
            events=[],
            confidence=confidence,
            needs_clarification=False,
        )

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
5. CREATE_EVENT - Creating new calendar events (schedule, add, create, book, set up)
6. UPDATE_EVENT - Modifying existing events (change, reschedule, move, update)
7. DELETE_EVENT - Removing events (cancel, delete, remove)
8. CLARIFICATION_FOLLOWUP - Follow-up responses to previous clarification questions
9. CLARIFICATION_NEEDED - Query is too ambiguous to process

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
"Schedule a meeting with John tomorrow at 2pm" → CREATE_EVENT
"Book a dentist appointment for next Friday" → CREATE_EVENT
"Add lunch with Sarah to my calendar" → CREATE_EVENT
"Change my 3pm meeting to 4pm" → UPDATE_EVENT
"Cancel my dentist appointment" → DELETE_EVENT
"therapy" (after asking about therapy) → CLARIFICATION_FOLLOWUP
"sfo" (after asking about flights) → CLARIFICATION_FOLLOWUP
"Show me meetings" → CLARIFICATION_NEEDED (missing time context)

Return JSON with this format:
{{
  "intent": "FETCH_EVENTS_SEMANTIC",
  "confidence": 0.95,
  "time_direction": "past_or_future_or_present",
  "is_followup": true_or_false,
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
        """Extract time parameters using deterministic parsing (replacing LLM-based approach)"""

        try:
            # Use the fixed time parsing logic from time_manager
            from ..core.time.time_manager import (
                parse_time_range,
                extract_date_range_from_query,
            )

            # First try the deterministic time parsing
            time_result = parse_time_range(user_query)

            if time_result.get("specific_date"):
                # Specific date found (like "tomorrow", "friday", "dec 8th")
                specific_date = time_result["specific_date"]
                start_time = specific_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                end_time = specific_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

                return {
                    "start_datetime": start_time.isoformat(),
                    "end_datetime": end_time.isoformat(),
                    "time_description": f"specific_date_{specific_date.strftime('%Y-%m-%d')}",
                    "time_direction": "present",
                    "confidence": 0.95,
                }

            elif time_result.get("date_range_start") and time_result.get(
                "date_range_end"
            ):
                # Date range found (like "nov 9-12", "june 15-20")
                start_time = time_result["date_range_start"]
                end_time = time_result["date_range_end"]

                return {
                    "start_datetime": start_time.isoformat(),
                    "end_datetime": end_time.isoformat(),
                    "time_description": f"date_range_{start_time.strftime('%Y-%m-%d')}_to_{end_time.strftime('%Y-%m-%d')}",
                    "time_direction": "present",
                    "confidence": 0.95,
                }

            else:
                # No specific date found, determine time direction and use appropriate range
                time_direction = user_context.get("time_direction", "present")

                # Check for past/future indicators in the query
                query_lower = user_query.lower()
                if any(
                    word in query_lower
                    for word in [
                        "last",
                        "previous",
                        "past",
                        "ago",
                        "before",
                        "yesterday",
                    ]
                ):
                    time_direction = "past"
                elif any(
                    word in query_lower
                    for word in ["next", "future", "upcoming", "tomorrow", "later"]
                ):
                    time_direction = "future"

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
                "time_description": f"general_{time_direction}_range",
                "time_direction": time_direction,
                "confidence": 0.7,
            }

        except Exception as e:
            self.logger.error(f"Time extraction error: {e}")

            # Fallback to default current day
            now = datetime.now()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            return {
                "start_datetime": start_time.isoformat(),
                "end_datetime": end_time.isoformat(),
                "time_description": "fallback_today",
                "time_direction": "present",
                "confidence": 0.3,
            }

    def semantic_event_matching(
        self, user_query: str, calendar_events: List[Dict], user_context: Dict
    ) -> Dict:
        """PROMPT 3: Semantic Event Matching with enhanced airport code support"""

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

**ENHANCED AIRPORT/FLIGHT MATCHING:**
- "sfo" matches: "San Francisco", "SFO", "San Francisco International", "SF", "Bay Area"
- "lax" matches: "Los Angeles", "LAX", "LA", "Los Angeles International"
- "flight" matches: "Flight", "airline", flight numbers like "F9 4593", "Delta 1234", "United 567"
- "trip to [city]" matches: events with that city name, airport codes, or travel-related terms
- Airport codes (3-letter): automatically expand to full city names for matching

**COMMON AIRPORT CODE EXPANSIONS:**
- SFO → San Francisco, SF, Bay Area
- LAX → Los Angeles, LA
- JFK → New York, NYC, Kennedy
- ORD → Chicago, Chi
- DFW → Dallas, Texas
- ATL → Atlanta, Georgia
- DEN → Denver, Colorado
- SEA → Seattle, Washington
- MIA → Miami, Florida
- BOS → Boston, Massachusetts

**FLIGHT NUMBER PATTERNS:**
- Look for patterns like: [A-Z][A-Z]?[0-9]+, flight numbers, airline codes
- Match "F9 4593" type patterns in event titles/descriptions

Return a JSON response:
{{
  "matches": [
    {{
      "event_id": "event_123",
      "title": "Event Title",
      "start_time": "2025-06-08T15:00:00",
      "confidence": 0.95,
      "match_reason": "Event title contains 'San Francisco' which matches airport code 'SFO' in query"
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

CRITICAL FORMATTING REQUIREMENTS:
1. ALWAYS put each event on a NEW LINE
2. Use line breaks (\\n) between each event
3. Use simple dashes (-) instead of bullet points for better display
4. Keep event details clear and readable
5. Be conversational and warm

**EXACT FORMATTING TEMPLATE:**
For multiple events:
"Here's what you have coming up:

- **Event 1 Title** at TIME
- **Event 2 Title** at TIME  
- **Event 3 Title** at TIME

Would you like more details?"

For single event:
"You have one event coming up:

- **Event Title** at TIME

Anything else you'd like to know?"

**SPECIFIC FORMAT RULES:**
- Start each event line with "- " (dash and space)
- Put event title in **bold**
- Include time clearly
- Add blank line before and after event list
- Keep response under 4 lines total

Generate a helpful, natural response following this EXACT format.
Return ONLY the response text, no JSON or markup."""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")

            # Post-process the response to ensure proper formatting
            formatted_response = self._post_process_response(
                response.strip(), calendar_results
            )
            return formatted_response
        except Exception as e:
            self.logger.error(f"Response generation error: {e}")
            if calendar_results:
                # Fallback formatting if LLM fails
                return self._create_fallback_response(calendar_results)
            else:
                return "I couldn't find any matching events in your calendar. Could you provide more details or try a different search term?"

    def _post_process_response(
        self, response: str, calendar_results: List[Dict]
    ) -> str:
        """Post-process the LLM response to ensure proper formatting"""

        # Replace bullet points with dashes for better display
        response = response.replace("•", "-")

        # Ensure proper line breaks - if the response seems to be all on one line
        # but contains multiple events, add line breaks
        if len(calendar_results) > 1 and "\n" not in response and "-" in response:
            # Split on dash and rejoin with proper line breaks
            parts = response.split("-")
            if len(parts) > 2:  # Has multiple events
                intro = parts[0].strip()
                events = [f"- {part.strip()}" for part in parts[1:] if part.strip()]
                response = f"{intro}\n\n" + "\n".join(events)

        # Ensure there are line breaks before and after event lists
        if "-" in response and not response.startswith("- "):
            lines = response.split("\n")
            formatted_lines = []
            for line in lines:
                if line.strip().startswith("-") and not line.startswith("\n"):
                    # Add blank line before event list if not already there
                    if formatted_lines and formatted_lines[-1].strip():
                        formatted_lines.append("")
                formatted_lines.append(line)
            response = "\n".join(formatted_lines)

        return response

    def _create_fallback_response(self, calendar_results: List[Dict]) -> str:
        """Create a fallback response when LLM processing fails"""
        event_count = len(calendar_results)

        if event_count == 1:
            event = calendar_results[0]
            title = event.get("title", event.get("summary", "Event"))
            start_time = event.get(
                "start_time", event.get("start", {}).get("dateTime", "")
            )

            try:
                if start_time:
                    dt_obj = datetime.fromisoformat(start_time.replace("Z", ""))
                    time_str = dt_obj.strftime("%I:%M %p on %B %d")
                else:
                    time_str = "Time TBD"
            except:
                time_str = str(start_time) if start_time else "Time TBD"

            return f"I found 1 event for you:\n\n- **{title}** at {time_str}\n\nAnything else you'd like to know?"
        else:
            return f"I found {event_count} events for you.\n\nWould you like me to show you the details?"

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
        """Perform smart month-by-month search with early termination and confidence-based stopping"""
        if not self.calendar_available or not target_calendars:
            return []

        try:
            service = self.get_calendar_service()
            if not service:
                return []

            now = datetime.now()
            found_events = []
            months_searched = 0

            # **SMART SEARCH LIMITS** - Prevent excessive searching
            query_lower = user_query.lower()

            # Determine max months based on query type and specificity
            if any(
                term in query_lower
                for term in ["today", "tomorrow", "this week", "next week"]
            ):
                max_months = 1  # Very specific time queries - search only 1 month
            elif any(
                term in query_lower
                for term in ["this month", "next month", "last month"]
            ):
                max_months = 2  # Month-specific queries - search 2 months
            elif any(
                term in query_lower for term in ["recent", "lately", "soon", "upcoming"]
            ):
                max_months = 3  # Recent/upcoming queries - search 3 months
            elif any(
                term in query_lower
                for term in ["last", "previous", "when was", "when is"]
            ):
                max_months = 6  # Historical queries - search 6 months
            else:
                max_months = 4  # Default for semantic searches - search 4 months

            # **CONFIDENCE TRACKING** - Stop when we find good matches
            confidence_threshold = 0.8  # High confidence threshold
            decent_matches = []  # Store medium confidence matches as backup

            self.logger.info(
                f"Starting smart incremental search: {search_type} in {time_direction} direction (max {max_months} months)"
            )

            while months_searched < max_months:
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

                        # **CONFIDENCE-BASED EARLY TERMINATION**
                        high_confidence_matches = [
                            event
                            for event in filtered_events
                            if event.get("confidence", 0) >= confidence_threshold
                        ]

                        medium_confidence_matches = [
                            event
                            for event in filtered_events
                            if 0.5 <= event.get("confidence", 0) < confidence_threshold
                        ]

                        if high_confidence_matches:
                            # Found high confidence matches - stop searching!
                            found_events = high_confidence_matches
                            self.logger.info(
                                f"Found {len(high_confidence_matches)} high-confidence events in {month_name} - stopping search"
                            )
                            break
                        elif medium_confidence_matches:
                            # Keep medium confidence matches as backup
                            decent_matches.extend(medium_confidence_matches)

                    else:
                        filtered_events = month_events

                    # For non-semantic searches, any events found = stop searching
                    if filtered_events and search_type != "semantic":
                        found_events = filtered_events
                        self.logger.info(
                            f"Found {len(found_events)} events in {month_name}"
                        )
                        break

                months_searched += 1

                # Break if we're searching present (only current month)
                if time_direction == "present":
                    break

                # **DIMINISHING RETURNS CHECK** - Stop if we're going too far back/forward
                if (
                    months_searched >= 2
                    and not decent_matches
                    and search_type == "semantic"
                ):
                    self.logger.info(
                        f"No decent matches found after {months_searched} months - stopping search early"
                    )
                    break

            # If no high-confidence matches but we have decent ones, use those
            if not found_events and decent_matches:
                found_events = decent_matches[:5]  # Limit to top 5 decent matches
                self.logger.info(
                    f"Using {len(found_events)} medium-confidence matches as fallback"
                )

            if not found_events:
                self.logger.info(
                    f"No events found after searching {months_searched} months (limit: {max_months})"
                )

            return found_events

        except Exception as e:
            self.logger.error(f"Error in incremental search: {e}")
            return []

    def _extract_comprehensive_event_details(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract comprehensive event details from user query using advanced LLM parsing"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )
        user_timezone = user_context.get("timezone", "America/New_York")

        prompt = f"""
You are an expert calendar assistant. Parse this natural language query into comprehensive event details.

Current date and time: {current_datetime}
User timezone: {user_timezone}
User query: "{user_query}"

**REQUIRED FIELDS:**
- summary: Event title/name
- start_datetime: Start time in ISO format (YYYY-MM-DDTHH:MM:SS)
- end_datetime: End time in ISO format (if not specified, add 1 hour to start)

**OPTIONAL FIELDS:**
- description: Event description/notes
- location: Physical or virtual location
- attendees: List of email addresses or names
- all_day: Boolean - true if all day event
- recurrence_rule: For repeating events (daily, weekly, monthly, etc.)
- reminder_minutes: List of reminder times in minutes before event [15, 60, 1440] (default [15])
- add_meet: Boolean - true if user wants Google Meet link
- calendar_name: Which calendar to use by name (extract from user query, default "primary")
- visibility: "default", "public", "private" (default "default")
- color_id: Event color (1-11) based on context or user preference
- busy_status: "busy" or "free" (default "busy")
- guests_can_modify: Boolean - can attendees edit event (default false)
- guests_can_invite_others: Boolean - can attendees add others (default true)
- guests_can_see_other_guests: Boolean - can attendees see guest list (default true)

**ADVANCED RECURRENCE PARSING:**
Parse complex recurrence patterns:
- "daily" → FREQ=DAILY
- "weekly" → FREQ=WEEKLY  
- "monthly" → FREQ=MONTHLY
- "every weekday" → FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
- "every Tuesday and Thursday" → FREQ=WEEKLY;BYDAY=TU,TH
- "first Monday of every month" → FREQ=MONTHLY;BYDAY=1MO
- "every 2 weeks" → FREQ=WEEKLY;INTERVAL=2
- "daily for 10 days" → FREQ=DAILY;COUNT=10
- "weekly until Dec 31" → FREQ=WEEKLY;UNTIL=20251231T235959Z

**SMART REMINDER PARSING:**
- "remind me 30 minutes before" → [30]
- "remind me an hour and 15 minutes before" → [60, 15]
- "remind me the day before" → [1440]
- "remind me a week before and an hour before" → [10080, 60]
- default to [15] if not specified

**SMART COLOR DETECTION:**
Assign colors based on event type:
- Work/business meetings → 1 (lavender)
- Personal/social → 2 (sage)
- Health/medical → 3 (grape)
- Exercise/fitness → 4 (flamingo)
- Travel → 5 (banana)
- Education/learning → 6 (tangerine)
- Deadlines/important → 7 (peacock)
- Family → 8 (graphite)
- Entertainment → 9 (blueberry)
- Food/dining → 10 (basil)
- Other → 11 (tomato)

**ATTENDEE PARSING:**
Extract emails and names intelligently:
- "meeting with john@company.com" → ["john@company.com"]
- "lunch with Sarah Johnson sarah.j@email.com" → [{{"email": "sarah.j@email.com", "name": "Sarah Johnson"}}]
- "team meeting with John, Sarah, and mike@work.com" → [{{"name": "John"}}, {{"name": "Sarah"}}, {{"email": "mike@work.com"}}]

**CALENDAR PARSING:**
Extract calendar names from user queries:
- "add to my jetski calendar" → calendar_name: "jetski"
- "create on my work calendar" → calendar_name: "work"
- "add to personal calendar" → calendar_name: "personal"
- "schedule in my family calendar" → calendar_name: "family"
- "put on my travel calendar" → calendar_name: "travel"
- "add to calendar" (no specific calendar) → calendar_name: "primary"

**SMART PARSING EXAMPLES:**
- "lunch with john@company.com tomorrow at noon" → attendees: [{{"email": "john@company.com"}}], start: tomorrow 12:00, end: tomorrow 13:00
- "daily standup at 9am starting Monday, remind me 5 minutes before" → recurrence: "FREQ=DAILY", reminder_minutes: [5]
- "all day conference next Friday, color it red" → all_day: true, color_id: 11
- "private meeting with CEO tomorrow 2pm, don't let others see guests" → visibility: "private", guests_can_see_other_guests: false
- "team meeting with Google Meet link" → add_meet: true
- "doctor appointment, mark as free time" → busy_status: "free", color_id: 3
- "weekly team standup every Tuesday at 10am for 6 weeks" → recurrence: "FREQ=WEEKLY;BYDAY=TU;COUNT=6"
- "add a block to my jetski calendar at 2pm today" → calendar_name: "jetski", start: today 14:00
- "schedule meeting on my work calendar tomorrow" → calendar_name: "work", start: tomorrow

**DATE/TIME PARSING - BE VERY PRECISE:**
- "tomorrow" = next day from current_datetime
- "next Friday" = next occurring Friday  
- "at 2pm" = 14:00:00 (NOT 23:30 or any other time!)
- "at noon" = 12:00:00
- "in the morning" = 09:00:00 (default)
- "in the afternoon" = 14:00:00 (default)
- "in the evening" = 18:00:00 (default)

**CRITICAL REQUIREMENTS:**
- ALWAYS convert times correctly: "2pm" = "14:00:00", NOT "23:30:00"
- ALWAYS create 1-hour duration if no end time specified
- Use the user's timezone: {user_timezone}
- If no specific duration mentioned, make it exactly 1 hour long

**VALIDATION:**
- If date/time is unclear or missing, set needs_clarification: true
- If title is missing, set needs_clarification: true  
- Always include clarification_question if needs_clarification is true

Return JSON format:
{{
  "summary": "Meeting with John",
  "start_datetime": "2025-06-09T14:00:00",
  "end_datetime": "2025-06-09T15:00:00",
  "description": "Discuss project updates",
  "location": "Conference Room A",
  "attendees": [{{"email": "john@company.com", "name": "John Smith"}}],
  "all_day": false,
  "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
  "reminder_minutes": [15, 60],
  "add_meet": false,
  "calendar_name": "primary",
  "visibility": "default",
  "color_id": 1,
  "busy_status": "busy",
  "guests_can_modify": false,
  "guests_can_invite_others": true,
  "guests_can_see_other_guests": true,
  "needs_clarification": false,
  "clarification_question": ""
}}

Return ONLY the JSON response."""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            result = json.loads(response)

            # Ensure default values for required fields
            result.setdefault("summary", "")
            result.setdefault("start_datetime", "")
            result.setdefault("end_datetime", "")
            result.setdefault("all_day", False)
            result.setdefault("needs_clarification", False)
            result.setdefault("clarification_question", "")
            result.setdefault("calendar_name", "primary")
            result.setdefault("reminder_minutes", [15])
            result.setdefault("add_meet", False)
            result.setdefault("visibility", "default")
            result.setdefault("busy_status", "busy")
            result.setdefault("guests_can_modify", False)
            result.setdefault("guests_can_invite_others", True)
            result.setdefault("guests_can_see_other_guests", True)

            # Auto-generate end time if missing but start time exists
            if result.get("start_datetime") and not result.get("end_datetime"):
                try:
                    start_dt = datetime.fromisoformat(
                        result["start_datetime"].replace("Z", "+00:00")
                    )
                    if result.get("all_day"):
                        # All day events end at 23:59:59 of the same day
                        end_dt = start_dt.replace(hour=23, minute=59, second=59)
                    else:
                        # Regular events default to 1 hour
                        end_dt = start_dt + timedelta(hours=1)
                    result["end_datetime"] = end_dt.isoformat()
                    self.logger.info(
                        f"Auto-generated 1-hour duration: {result['start_datetime']} -> {result['end_datetime']}"
                    )
                except Exception as e:
                    self.logger.warning(f"Could not auto-generate end time: {e}")

            # Force 1-hour duration if both times exist but are the same
            if (
                result.get("start_datetime")
                and result.get("end_datetime")
                and result["start_datetime"] == result["end_datetime"]
            ):
                try:
                    start_dt = datetime.fromisoformat(
                        result["start_datetime"].replace("Z", "+00:00")
                    )
                    end_dt = start_dt + timedelta(hours=1)
                    result["end_datetime"] = end_dt.isoformat()
                    self.logger.info(f"Fixed same start/end times to 1-hour duration")
                except Exception as e:
                    self.logger.warning(f"Could not fix same start/end times: {e}")

            return result

        except (json.JSONDecodeError, Exception) as e:
            self.logger.error(f"Event extraction error: {e}")
            return {
                "summary": "",
                "start_datetime": "",
                "end_datetime": "",
                "needs_clarification": True,
                "clarification_question": "Could you provide more details about the event, including the title and when you'd like to schedule it?",
            }

    def _generate_event_creation_response(
        self, created_event: Dict[str, Any], original_query: str
    ) -> str:
        """Generate a conversational response for successful event creation"""

        try:
            summary = created_event.get("summary", "Event")
            start_time = created_event.get("start", {}).get("dateTime", "")
            location = created_event.get("location", "")
            calendar_name = created_event.get("calendar_name", "")

            # Parse start time for friendly display
            time_display = ""
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    time_display = dt.strftime("%A, %B %d at %I:%M %p")
                except:
                    time_display = start_time

            # Build response
            response_parts = [f"✅ I've successfully created your event: **{summary}**"]

            if time_display:
                response_parts.append(f"📅 Scheduled for {time_display}")

            if location:
                response_parts.append(f"📍 Location: {location}")

            # Add calendar info if not primary
            if calendar_name and calendar_name != "primary":
                response_parts.append(f"📋 Added to your **{calendar_name}** calendar")

            # Add helpful note
            response_parts.append("\nThe event has been added to your Google Calendar!")

            return "\n".join(response_parts)

        except Exception as e:
            self.logger.error(f"Error generating creation response: {e}")
            return f"✅ I've successfully created your event! Check your Google Calendar to see the details."

    def _resolve_calendar_name_to_id(self, service, calendar_name: str) -> str:
        """Resolve a calendar name to calendar ID"""

        # If it's already "primary" or looks like a calendar ID, return as-is
        if calendar_name == "primary" or "@" in calendar_name:
            return calendar_name

        try:
            # Get user's calendar list
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get("items", [])

            # First try exact name match (case insensitive)
            calendar_name_lower = calendar_name.lower()
            for calendar in calendars:
                calendar_summary = calendar.get("summary", "").lower()
                calendar_summary_override = calendar.get("summaryOverride", "").lower()

                if (
                    calendar_summary == calendar_name_lower
                    or calendar_summary_override == calendar_name_lower
                ):
                    self.logger.info(
                        f"Found exact calendar match: '{calendar_name}' -> {calendar['id']}"
                    )
                    return calendar["id"]

            # Then try partial match (contains)
            for calendar in calendars:
                calendar_summary = calendar.get("summary", "").lower()
                calendar_summary_override = calendar.get("summaryOverride", "").lower()

                if (
                    calendar_name_lower in calendar_summary
                    or calendar_name_lower in calendar_summary_override
                ):
                    self.logger.info(
                        f"Found partial calendar match: '{calendar_name}' -> {calendar['id']}"
                    )
                    return calendar["id"]

            # If no match found, use primary
            self.logger.warning(f"Calendar '{calendar_name}' not found, using primary")
            return "primary"

        except Exception as e:
            self.logger.error(f"Error resolving calendar name '{calendar_name}': {e}")
            return "primary"


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
        # Category 5: Event Creation Queries
        "Schedule a meeting with John tomorrow at 2pm",
        "Book a dentist appointment for next Friday at 10am",
        "Add lunch with Sarah to my calendar for tomorrow at noon",
        "Create a daily standup meeting at 9am starting Monday",
        "Set up an all-day conference event for next week",
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
