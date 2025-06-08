"""
Advanced Prompt Engineering for ORII Calendar Assistant
======================================================

This module implements a sophisticated multi-stage prompt engineering strategy
for natural language calendar queries. It includes 5 specialized prompts:

1. Intent Classification
2. Semantic Event Matching
3. Time-Based Fetching
4. Conversational Response Generation
5. Clarification Requests

Usage:
    processor = CalendarQueryProcessor()
    result = await processor.process_calendar_query(user_query, user_context)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import pytz

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


class CalendarQueryProcessor:
    """Advanced calendar query processor using structured prompts"""

    def __init__(self, llm_client=None):
        """Initialize the processor with an LLM client"""
        self.llm_client = llm_client
        if not llm_client:
            try:
                from .llm_client import get_llm_client

                self.llm_client = get_llm_client()
            except ImportError:
                raise Exception("LLM client required for advanced prompt processing")

    async def process_calendar_query(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        calendar_events: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryResult:
        """
        Process a calendar query using the advanced prompt strategy

        Args:
            user_query: The user's natural language query
            user_context: Context including timezone, current time, etc.
            calendar_events: Optional pre-fetched calendar events

        Returns:
            QueryResult with intent, response, and events
        """
        try:
            # Step 1: Classify intent
            intent_result = await self.classify_intent(user_query, user_context)
            intent = intent_result["intent"]
            confidence = intent_result["confidence"]

            logger.info(f"Classified intent: {intent} (confidence: {confidence})")

            # Handle low confidence or ambiguous queries
            if confidence < 0.7 or intent == "CLARIFICATION_NEEDED":
                clarification = await self.request_clarification(
                    user_query, intent_result.get("ambiguity_reason", "unclear_intent")
                )
                return QueryResult(
                    intent=intent,
                    response=clarification,
                    events=[],
                    confidence=confidence,
                    needs_clarification=True,
                    clarification_question=clarification,
                )

            # Step 2: Route to appropriate handler
            if intent == "GENERAL_CHAT":
                response = await self.handle_general_chat(user_query)
                return QueryResult(intent, response, [], confidence, False)

            elif intent == "CALENDAR_INFO":
                response = await self.handle_calendar_info(user_query)
                return QueryResult(intent, response, [], confidence, False)

            elif intent == "FETCH_EVENTS_TIME":
                return await self.handle_time_based_query(user_query, user_context)

            elif intent == "FETCH_EVENTS_SEMANTIC":
                return await self.handle_semantic_query(
                    user_query, user_context, calendar_events
                )

            else:
                # Fallback
                response = "I'm not sure how to help with that. Could you please rephrase your question?"
                return QueryResult(intent, response, [], confidence, True, response)

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            error_response = "Sorry, I encountered an error processing your request. Please try again."
            return QueryResult("ERROR", error_response, [], 0.0, False)

    async def classify_intent(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Classify the user's intent using the structured prompt"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )
        user_timezone = user_context.get("timezone", "UTC")

        prompt = f"""
You are ORII, an intelligent calendar assistant. Analyze the user's query and classify their intent.

Current date and time: {current_datetime}
User timezone: {user_timezone}

User query: "{user_query}"

Classify the intent into ONE of these categories:

1. GENERAL_CHAT - Non-calendar related questions (greetings, how are you, weather, etc.)
2. CALENDAR_INFO - Questions about calendar access, how the system works
3. FETCH_EVENTS_TIME - Time-based calendar queries (today, tomorrow, next week, etc.)
4. FETCH_EVENTS_SEMANTIC - Semantic event searches (therapy, dentist, meetings with person X)
5. CLARIFICATION_NEEDED - Query is too ambiguous to process

Examples:
"Hi how are you?" → GENERAL_CHAT
"What calendars can you access?" → CALENDAR_INFO  
"What do I have tomorrow?" → FETCH_EVENTS_TIME
"When was my last therapy session?" → FETCH_EVENTS_SEMANTIC
"Show me meetings" → CLARIFICATION_NEEDED (missing time context)

Return a JSON response with:
{{
  "intent": "INTENT_NAME",
  "confidence": 0.95,
  "reasoning": "Brief explanation of why this intent was chosen",
  "ambiguity_reason": "Explanation if CLARIFICATION_NEEDED"
}}

Return ONLY the JSON response.
"""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error in intent classification: {e}")
            return {
                "intent": "CLARIFICATION_NEEDED",
                "confidence": 0.0,
                "reasoning": "Failed to parse intent",
                "ambiguity_reason": "system_error",
            }

    async def extract_time_parameters(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract time parameters from a time-based query"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )
        user_timezone = user_context.get("timezone", "UTC")

        prompt = f"""
You are extracting time parameters from a calendar query.

User query: "{user_query}"
Current date and time: {current_datetime}
User timezone: {user_timezone}

Parse the temporal expressions and convert to specific date ranges:

Examples:
- "today" → start: 2025-06-08 00:00:00, end: 2025-06-08 23:59:59
- "tomorrow" → start: 2025-06-09 00:00:00, end: 2025-06-09 23:59:59  
- "next week" → start: 2025-06-09 00:00:00, end: 2025-06-15 23:59:59
- "this weekend" → start: 2025-06-14 00:00:00, end: 2025-06-15 23:59:59
- "next Monday" → start: 2025-06-09 00:00:00, end: 2025-06-09 23:59:59

Return JSON:
{{
  "start_datetime": "2025-06-08T00:00:00",
  "end_datetime": "2025-06-08T23:59:59",
  "time_description": "today",
  "confidence": 0.98
}}

If time cannot be parsed, set confidence to 0.0.
Return ONLY the JSON response.
"""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error extracting time parameters: {e}")
            return {
                "start_datetime": None,
                "end_datetime": None,
                "time_description": "unknown",
                "confidence": 0.0,
            }

    async def semantic_event_matching(
        self,
        user_query: str,
        calendar_events: List[Dict[str, Any]],
        user_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Find semantic matches for events using the structured prompt"""

        user_timezone = user_context.get("timezone", "UTC")
        current_date = user_context.get("current_datetime", datetime.now().isoformat())

        # Format events for the prompt
        events_json = json.dumps(calendar_events, indent=2, default=str)

        prompt = f"""
You are analyzing calendar events to find semantic matches for a user query.

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
Return ONLY the JSON response.
"""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error in semantic matching: {e}")
            return {"matches": [], "total_matches": 0}

    async def generate_conversational_response(
        self,
        user_query: str,
        detected_intent: str,
        calendar_results: List[Dict[str, Any]],
        user_context: Dict[str, Any],
    ) -> str:
        """Generate a natural conversational response"""

        current_datetime = user_context.get(
            "current_datetime", datetime.now().isoformat()
        )

        # Format calendar results for the prompt
        results_text = (
            json.dumps(calendar_results, indent=2, default=str)
            if calendar_results
            else "No events found"
        )

        prompt = f"""
You are ORII, a friendly and helpful calendar assistant. Generate a natural, conversational response to the user.

Context:
- User query: "{user_query}"
- Intent: {detected_intent}
- Calendar results: {results_text}
- Current time: {current_datetime}

Response guidelines:
1. Be conversational and warm, not robotic
2. Use natural language, avoid technical jargon
3. If no events found, be helpful and suggest alternatives
4. If ambiguous query, ask specific clarifying questions
5. For general chat, be friendly but redirect to calendar help
6. Present calendar information in an easy-to-read format

Response style examples:
❌ "Query processed. 2 events retrieved for specified timeframe."
✅ "I found 2 events coming up for you tomorrow!"

❌ "No semantic matches found in database."
✅ "I couldn't find any therapy sessions in your calendar. Would you like me to search for appointments with specific doctors instead?"

❌ "Intent classification: GENERAL_CHAT"
✅ "Hi there! I'm doing great, thanks for asking. How can I help you with your calendar today?"

For event lists, format like:
"Here's what you have coming up:
• **2:00 PM - Meeting with John** (Conference Room A)
• **4:30 PM - Dentist Appointment** (Dr. Smith's Office)

Would you like more details about any of these?"

Generate a helpful, natural response based on the context provided.
Return ONLY the response text, no JSON or markup.
"""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating conversational response: {e}")
            return "I found your information, but I'm having trouble formatting the response. Please try asking again."

    async def request_clarification(
        self, user_query: str, ambiguity_reason: str
    ) -> str:
        """Generate a clarification question for ambiguous queries"""

        prompt = f"""
The user's query is ambiguous and needs clarification.

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
Return ONLY the clarification question, no JSON or markup.
"""

        try:
            response = self.llm_client.get_completion(prompt, model="gpt-4")
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating clarification: {e}")
            return (
                "Could you please provide more details about what you're looking for?"
            )

    async def handle_general_chat(self, user_query: str) -> str:
        """Handle general chat queries"""
        general_responses = {
            "greeting": "Hi there! I'm doing great, thanks for asking. How can I help you with your calendar today?",
            "how_are_you": "I'm doing well! I'm here to help you manage your calendar. What would you like to know about your schedule?",
            "weather": "I don't have access to weather information, but I can help you with your calendar! Is there anything on your schedule you'd like to know about?",
            "default": "I'm here to help you with your calendar! You can ask me about your upcoming events, schedule meetings, or search for past appointments.",
        }

        query_lower = user_query.lower()
        if any(word in query_lower for word in ["hi", "hello", "hey"]):
            return general_responses["greeting"]
        elif any(word in query_lower for word in ["how are you", "how're you"]):
            return general_responses["how_are_you"]
        elif "weather" in query_lower:
            return general_responses["weather"]
        else:
            return general_responses["default"]

    async def handle_calendar_info(self, user_query: str) -> str:
        """Handle questions about calendar system capabilities"""
        return """I'm ORII, your AI calendar assistant! I can help you with:

• **View your schedule** - "What do I have today?" or "Show me next week"
• **Find specific events** - "When was my last dentist appointment?"
• **Search by people** - "When did I last meet with John?"
• **Semantic search** - "Show me my workout sessions" or "Find my therapy appointments"

I have access to your Google Calendar and can understand natural language queries. Just ask me anything about your schedule!"""

    async def handle_time_based_query(
        self, user_query: str, user_context: Dict[str, Any]
    ) -> QueryResult:
        """Handle time-based calendar queries"""

        # Extract time parameters
        time_params = await self.extract_time_parameters(user_query, user_context)

        if time_params["confidence"] < 0.7:
            clarification = await self.request_clarification(user_query, "unclear_time")
            return QueryResult(
                intent="FETCH_EVENTS_TIME",
                response=clarification,
                events=[],
                confidence=time_params["confidence"],
                needs_clarification=True,
                clarification_question=clarification,
            )

        # Here you would fetch events from the calendar API using the time parameters
        # For now, returning a placeholder response
        events = []  # This would be replaced with actual calendar fetching

        response = await self.generate_conversational_response(
            user_query, "FETCH_EVENTS_TIME", events, user_context
        )

        return QueryResult(
            intent="FETCH_EVENTS_TIME",
            response=response,
            events=events,
            confidence=time_params["confidence"],
            needs_clarification=False,
        )

    async def handle_semantic_query(
        self,
        user_query: str,
        user_context: Dict[str, Any],
        calendar_events: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryResult:
        """Handle semantic event searches"""

        if not calendar_events:
            # This would fetch a larger range of events for semantic matching
            calendar_events = []  # Placeholder - implement actual fetching

        # Perform semantic matching
        matches = await self.semantic_event_matching(
            user_query, calendar_events, user_context
        )
        matched_events = matches.get("matches", [])

        response = await self.generate_conversational_response(
            user_query, "FETCH_EVENTS_SEMANTIC", matched_events, user_context
        )

        return QueryResult(
            intent="FETCH_EVENTS_SEMANTIC",
            response=response,
            events=matched_events,
            confidence=0.8,  # Base confidence for semantic matching
            needs_clarification=False,
        )


# Test function for the 15 query categories
async def test_prompt_strategy():
    """Test the prompt strategy with the 15 defined query categories"""

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

    processor = CalendarQueryProcessor()
    user_context = {
        "current_datetime": datetime.now().isoformat(),
        "timezone": "America/New_York",
    }

    results = []
    for query in test_queries:
        try:
            result = await processor.process_calendar_query(query, user_context)
            results.append(
                {
                    "query": query,
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "needs_clarification": result.needs_clarification,
                }
            )
        except Exception as e:
            results.append({"query": query, "error": str(e)})

    return results


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_prompt_strategy())
