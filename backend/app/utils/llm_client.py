"""
LLM client for the application.

This module provides a client for LLM services.
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import random
import re
import dateutil.parser
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Changed from CRITICAL to INFO


class LLMClient:
    """Client for LLM services."""

    def __init__(self):
        """Initialize the LLM client.

        Raises:
            Exception: If OpenAI API key is not set or initialization fails
        """
        self.api_key = os.environ.get("OPENAI_API_KEY")

        if not self.api_key:
            logger.error("OpenAI API key not found")
            raise Exception("OpenAI API key not found in environment variables")

        try:
            import openai

            openai.api_key = self.api_key
            self.client = openai.OpenAI(api_key=self.api_key)
            self.initialized = True
            logger.info("OpenAI client initialized successfully")
        except ImportError:
            logger.error("Failed to import OpenAI package")
            raise Exception(
                "OpenAI package not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            raise Exception(f"Failed to initialize OpenAI client: {str(e)}")

    def get_completion(self, prompt: str, model: str = "gpt-3.5-turbo") -> str:
        """Get a completion from the LLM.

        Args:
            prompt: The prompt to get a completion for
            model: The model to use

        Returns:
            Completion text

        Raises:
            Exception: If there's an error getting the completion
        """
        if self.initialized:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful assistant specializing in calendar management.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=1000,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Error getting completion: {e}")
                # Don't fall back to mock, raise the exception to ensure real data is used
                raise Exception(f"Error accessing language model: {str(e)}")
        else:
            # No mock implementation - raise an exception
            raise Exception("LLM client not initialized and mock services disabled")

    def extract_event_details(
        self, query: str, time_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract event details from a query.

        Args:
            query: The user query
            time_info: Time information extracted from the query

        Returns:
            Dictionary with event details

        Raises:
            Exception: If LLM is not available
        """
        # Check that LLM is initialized
        if not self.initialized:
            raise Exception("LLM client not initialized and mock services disabled")

        try:
            prompt = f"""
            Extract event details from the following query:
            "{query}"
            
            Time information already extracted:
            {time_info}
            
            Return a JSON object with these fields:
            - summary: the event title
            - description: a detailed description
            - start_time: start time
            - end_time: end time
            - location: event location (if specified)
            - attendees: list of attendees (if specified)
            - is_all_day: boolean indicating if it's an all-day event
            """

            result = self.get_completion(prompt)
            try:
                event_details = json.loads(result)
                return event_details
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing event details JSON: {e}")
                raise Exception(
                    f"Failed to parse event details from LLM response: {str(e)}"
                )
        except Exception as e:
            logger.error(f"Error extracting event details: {e}")
            raise Exception(f"Failed to extract event details: {str(e)}")

    def classify_intent(
        self,
        query: str,
        time_info: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Classify the intent of a query

        Args:
            query: User query string
            time_info: Time information extracted from the query
            conversation_context: Optional conversation context from previous interactions

        Returns:
            Intent classification result
        """
        prompt = self._create_intent_classification_prompt(
            query, time_info, conversation_context
        )
        logger.debug(f"Intent classification prompt length: {len(prompt)}")

        # Get completion from LLM
        response = self.get_completion(prompt)

        try:
            # Parse JSON response
            intent_data = json.loads(response)
            return intent_data
        except Exception as e:
            logger.error(f"Error parsing intent classification response: {e}")
            logger.debug(f"Raw response: {response}")
            # Fallback to simple search intent
            return {
                "intent_type": "search_events",
                "is_past": False,
                "days_range": 7,
                "reverse_chronological": False,
                "search_terms": [],
                "specified_calendar": None,
                "needs_calendar_data": True,
            }

    def _create_intent_classification_prompt(
        self,
        query: str,
        time_info: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a prompt for intent classification

        Args:
            query: User query string
            time_info: Time information extracted from the query
            conversation_context: Optional conversation context

        Returns:
            Intent classification prompt
        """
        # Add conversation context if available
        context_text = ""
        if (
            conversation_context
            and len(conversation_context.get("chat_history", [])) > 0
        ):
            # Format the last 2-3 turns of conversation
            history = conversation_context.get("chat_history", [])
            # Take at most the 3 most recent turns (6 messages - 3 user, 3 assistant)
            recent_history = history[-6:] if len(history) > 6 else history

            context_text = "\nConversation history (most recent first):\n"
            for i in range(len(recent_history) - 1, -1, -2):
                if i > 0:  # Make sure we have a pair
                    context_text += f"User: {recent_history[i-1]['content']}\n"
                    context_text += f"Assistant: {recent_history[i]['content']}\n\n"

            context_text += "This is important for understanding follow-up questions that refer to entities or topics from previous turns.\n"

        prompt = f"""
        Analyze the following calendar assistant query and determine the user's intent.
        Query: "{query}"
        
        The system has already performed date/time parsing and extracted the following temporal information:
        {json.dumps(time_info, default=str)}
        
        {context_text}
        
        Consider the context carefully in your classification. Pay special attention to:
        - Whether this seems to be a follow-up question to the previous conversation
        - Whether the query is asking about a specific date
        - Whether that date is in the past or future
        - If the query is asking about the current date/time
        - If it's asking for a range of dates or a specific day
        - If it's asking about which calendars the assistant has access to
        - If the user is specifying a particular calendar to search (e.g., "in my work calendar", "on my personal calendar")
        - If the user is asking to see/list all available calendars
        
        Very important: If the query is a follow-up question like "how about tomorrow?" or "what about next week?", use the context to determine what the user is really asking.
        
        Return your analysis as a JSON object with the following fields:
        - intent_type: One of ["search_events", "create_event", "time_date", "greeting", "assistant_info", "calendar_list", "calendar_access_query"]
        - is_past: Boolean, whether the query refers to past events
        - days_range: Integer, the number of days to look back/forward
        - needs_calendar_data: Boolean, whether calendar data needs to be fetched
        - is_creation: Boolean, whether the user wants to create an event
        - reverse_chronological: Boolean, whether results should be shown in reverse chronological order
        - search_terms: List of relevant search terms for filtering events, or null if not applicable
        - specified_calendar: String containing the name of the calendar if the user specified one (e.g., "work", "personal", "family"), or null if not specified
        
        If the query is explicitly asking about the current date or time (e.g., "what day is it today"), make sure to classify it as "time_date" intent.
        
        If the query is asking about which calendars the assistant can see, access, or has permission to, classify it as "calendar_access_query" intent.
        
        If the user mentions a specific calendar to search in (e.g., "check my work calendar", "events in my family calendar"), extract the calendar name (like "work" or "family") and include it in the specified_calendar field.
        """
        return prompt

    def extract_date_understanding(self, query: str) -> Dict[str, Any]:
        """Extract date understanding from a query.

        Args:
            query: The user query

        Returns:
            Dictionary with date information
        """
        # Simple stub implementation for testing
        result = {
            "is_past": False,
            "days_range": 1,
            "reverse_chronological": False,
            "specific_date": datetime.now(),
            "date_range_start": None,
            "date_range_end": None,
        }

        # Add some basic pattern matching
        if "tomorrow" in query.lower():
            result["specific_date"] = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            result["days_range"] = 1
        elif "yesterday" in query.lower():
            result["specific_date"] = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            result["is_past"] = True
            result["days_range"] = 1
        elif "next week" in query.lower():
            result["days_range"] = 7

        return result

    def parse_date_understanding(
        self, query: str, time_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Parse date understanding from a query using LLM.

        Args:
            query: The user query
            time_context: Temporal context information

        Returns:
            Dictionary with date information
        """
        logger.info(f"Parsing date understanding for query: {query}")

        # Check for explicit month+day mentions first (e.g., "May 18")
        query_lower = query.lower()

        # Common date patterns
        month_day_pattern = r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}\b"

        month_match = re.search(month_day_pattern, query, re.IGNORECASE)
        if month_match:
            try:
                date_str = month_match.group(0)
                # Try to parse the date string with current year
                now = datetime.now()
                parsed_date = dateutil.parser.parse(f"{date_str}, {now.year}")

                # Determine if past tense is used
                past_tense = any(
                    word in query_lower for word in ["did", "was", "had", "happened"]
                )

                # If date is in the past and not using past tense, assume next year
                if parsed_date < now and not past_tense:
                    next_year = now.year + 1
                    parsed_date = parsed_date.replace(year=next_year)

                # Return structured data
                return {
                    "is_past": parsed_date < now,
                    "days_range": 1,
                    "reverse_chronological": False,
                    "specific_date": parsed_date,
                    "date_range_start": None,
                    "date_range_end": None,
                    "date_mentioned": True,
                }
            except Exception as e:
                logger.warning(f"Error parsing explicit date pattern: {e}")

        # If we reach here, use the LLM analysis
        try:
            # Include time_context in prompt if available
            if time_context:
                current_context = f"""
                Current temporal context:
                - Current date: {time_context.get('current_date')}
                - Current time: {time_context.get('current_time')}
                - Last mentioned date: {time_context.get('last_mentioned_date')}
                """
            else:
                current_context = ""

            prompt = f"""
            Analyze the date and time information in this query: "{query}"
            
            {current_context}
            
            Identify:
            1. If it refers to a specific date or a date range
            2. If it's referring to the past or future
            3. If there's a specific date mentioned, what date it is
            4. How many days should be considered in the date range
            
            Return a JSON with these fields:
            - is_past: Boolean, whether query is about past events
            - days_range: Integer, number of days to look ahead/back
            - reverse_chronological: Boolean, whether results should be in reverse chronological order
            - specific_date: Date object (or null if no specific date)
            - date_range_start: Date object (or null if no range)
            - date_range_end: Date object (or null if no range)
            
            For a query like "Show me events from last Monday to Friday", return the specific start and end dates.
            """

            response = self.get_completion(prompt)

            try:
                result = json.loads(response)

                # Make sure dates are properly parsed from strings to datetime
                for key in ["specific_date", "date_range_start", "date_range_end"]:
                    if key in result and result[key] and isinstance(result[key], str):
                        try:
                            result[key] = dateutil.parser.parse(result[key])
                        except:
                            result[key] = None

                return result
            except:
                # Fall back to basic extraction
                return self.extract_date_understanding(query)

        except Exception as e:
            logger.warning(f"LLM date parsing failed: {e}")
            return self.extract_date_understanding(query)

    def match_events_semantically(
        self, search_term: str, event_titles: List[str]
    ) -> List[Dict[str, Any]]:
        """Match events semantically based on search term.

        Args:
            search_term: The search term
            event_titles: List of event titles

        Returns:
            List of matching events with indices
        """
        # Simple stub implementation for testing
        matches = []

        for i, title in enumerate(event_titles):
            # Do simple substring matching
            if search_term.lower() in title.lower():
                matches.append(
                    {
                        "event_index": i,
                        "confidence": 0.9,
                        "reasoning": f"Direct substring match of '{search_term}' in '{title}'",
                    }
                )

        return matches

    def generate_conversational_response(
        self, query: str, results: Dict[str, Any], conversation_context: Dict[str, Any]
    ) -> str:
        """Generate a conversational response.

        Args:
            query: The user query
            results: The results from processing the query
            conversation_context: Context from the conversation

        Returns:
            A conversational response
        """
        try:
            intent_type = results.get("intent_type")

            if "error" in results:
                return f"I'm sorry, I encountered an error: {results.get('error')}"

            # For calendar queries, create a natural language response
            if intent_type == "calendar_query" or intent_type == "search_events":
                events = results.get("events", [])
                time_description = ""

                # Extract time info for context
                if "specific_date" in results:
                    specific_date = results.get("specific_date")
                    if specific_date:
                        from datetime import datetime

                        if isinstance(specific_date, str):
                            try:
                                specific_date = datetime.fromisoformat(specific_date)
                            except:
                                pass
                        if isinstance(specific_date, datetime):
                            time_description = (
                                f" for {specific_date.strftime('%A, %B %d')}"
                            )
                elif "date" in results:
                    time_description = f" for {results['date']}"

                if not events:
                    return f"I checked your calendar{time_description} and it looks like you don't have any events scheduled. Your schedule is clear!"

                # Format the event information for the LLM
                event_descriptions = []
                for event in events:
                    if isinstance(event, dict):
                        title = event.get("title", "Untitled event")
                        start = event.get("start", "")
                        end = event.get("end", "")
                        location = event.get("location", "")
                        description = event.get("description", "")
                        event_descriptions.append(
                            f"Title: {title}, Start: {start}, End: {end}, Location: {location}"
                        )
                    else:
                        # If it's just a string, use it directly
                        event_descriptions.append(str(event))

                # Add specific instructions for date-specific queries
                date_focus_instructions = ""
                if (
                    results.get("specific_date_query", False)
                    or "specific_date" in results
                ):
                    date_focus_instructions = "The user asked about a specific date, so ONLY include events for that exact date in your response. Don't mention events on any other dates."

                # Create a prompt for generating a conversational response
                prompt = f"""
                Generate a conversational, helpful response about the following calendar events{time_description}.
                Make it sound natural and friendly. Include key details but be concise.
                
                {date_focus_instructions}
                
                Events:
                {chr(10).join(f"- {event}" for event in event_descriptions)}
                
                User query: {query}
                """

                response = self.get_completion(prompt)
                return response

            elif intent_type == "time_date":
                if "date" in results:
                    return f"It's {results['date']}."

            elif intent_type == "greeting":
                return "Hello! I'm your calendar assistant. How can I help you with your schedule today?"

            # Default response for unknown intent types
            return "I'm not sure how to help with that specific request. I can show you your calendar events, help schedule meetings, or find specific appointments. What would you like to know about your calendar?"

        except Exception as e:
            logger.error(f"Error generating conversational response: {e}")
            # Fallback to a simple response
            return "I found some information about your calendar, but I'm having trouble presenting it in a natural way. Would you like me to show you the basic details?"


_llm_client_instance = None


def get_llm_client():
    """Get a singleton instance of the LLM client.

    Returns:
        LLM client instance
    """
    global _llm_client_instance

    if _llm_client_instance is None:
        logger.info("Initializing new LLM client instance")
        _llm_client_instance = LLMClient()

    return _llm_client_instance
