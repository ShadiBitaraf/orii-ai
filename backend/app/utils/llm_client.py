"""
LLM client for calendar assistant.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta

# Import client libraries based on availability
try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# try:
#     import anthropic

#     ANTHROPIC_AVAILABLE = True
# except ImportError:
#     ANTHROPIC_AVAILABLE = False

# Get the logger
from .logger import get_logger

logger = get_logger()


class LLMClient:
    """Client for interacting with LLMs to enhance calendar features"""

    def __init__(self, provider="openai"):
        """
        Initialize the LLM client.

        Args:
            provider: The LLM provider to use ("openai" or "anthropic")
        """
        self.provider = provider
        self.conversation_context = {"date_references": [], "last_mentioned_date": None}
        self.model = "gpt-3.5-turbo"  # Default model

        # Set up the client based on provider
        if provider == "openai" and OPENAI_AVAILABLE:
            # Initialize OpenAI client
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.warning(
                    "OpenAI API key not found. LLM functionality will be limited."
                )
            else:
                self.client = openai.OpenAI(api_key=api_key)

        # elif provider == "anthropic" and ANTHROPIC_AVAILABLE:
        #     # Initialize Anthropic client
        #     api_key = os.environ.get("ANTHROPIC_API_KEY")
        #     if not api_key:
        #         logger.warning(
        #             "Anthropic API key not found. LLM functionality will be limited."
        #         )
        #     else:
        #         self.client = anthropic.Anthropic(api_key=api_key)
        else:
            logger.warning(f"Provider {provider} not available or not supported.")
            self.client = None

    def update_date_context(self, date_obj: datetime):
        """Update the conversation context with date information"""
        self.conversation_context["last_mentioned_date"] = date_obj
        self.conversation_context["date_references"].append(date_obj)

        # Keep only the last 5 date references
        if len(self.conversation_context["date_references"]) > 5:
            self.conversation_context["date_references"].pop(0)

    def get_completion(self, prompt: str, model: str = "gpt-3.5-turbo") -> str:
        """
        Get a completion from the LLM.

        Args:
            prompt: The prompt to send to the LLM
            model: The model to use

        Returns:
            The LLM's response
        """
        if not self.client:
            logger.error("LLM client not initialized.")
            return "LLM service unavailable."

        try:
            # Add context about date/time to the prompt
            enhanced_prompt = self._add_time_context(prompt)

            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": enhanced_prompt}],
                    temperature=0.2,
                )
                return response.choices[0].message.content

            elif self.provider == "anthropic":
                response = self.client.completions.create(
                    model="claude-2" if model == "gpt-4" else "claude-instant-1",
                    prompt=enhanced_prompt,
                    max_tokens_to_sample=1000,
                    temperature=0.2,
                )
                return response.completion

        except Exception as e:
            logger.error(f"Error getting LLM completion: {e}")
            return f"Error: {str(e)}"

    def _add_time_context(self, prompt: str) -> str:
        """Add time context to the prompt for better date understanding"""
        now = datetime.now()

        time_context = f"""
Current date and time information:
- Current date: {now.strftime('%Y-%m-%d')}
- Current day: {now.strftime('%A')}
- Current time: {now.strftime('%H:%M')}
"""

        # Add conversation context if available
        if self.conversation_context["last_mentioned_date"]:
            time_context += f"- Last mentioned date: {self.conversation_context['last_mentioned_date'].strftime('%Y-%m-%d')}\n"

        return f"{time_context}\n\n{prompt}"

    def parse_datetime_intent(self, query, date_info):
        """Enhance date/time understanding using the LLM.

        Args:
            query: User's natural language query
            date_info: Initial date information from the parser

        Returns:
            Enhanced date information if improvements were made, otherwise original date_info
        """
        print(f"[DEBUG] LLM parse_datetime_intent called for query: '{query}'")
        print(f"[DEBUG] Initial date_info: {date_info}")

        # If we already have a specific date, update conversation context
        if date_info.get("specific_date"):
            print(
                f"[DEBUG] Updating conversation context with specific_date: {date_info['specific_date']}"
            )

            # Check if this is a simple date case that doesn't need LLM enhancement
            if date_info.get("date_mentioned") and not date_info.get("time_mentioned"):
                # Most simple date queries don't need enhancement
                print(
                    f"[DEBUG] Simple date case detected, returning original date_info"
                )
                return date_info

        # For relative date references like "last 3 days", use the provided values
        # if they include date_range_start and date_range_end
        if (
            date_info.get("relative_reference") == "past_days"
            and date_info.get("date_range_start")
            and date_info.get("date_range_end")
        ):
            print(
                f"[DEBUG] Using pre-calculated date range for '{date_info['relative_reference']}' reference"
            )
            return date_info

        try:
            # Prepare a prompt that includes the query and existing date info
            prompt = f"""
I need to understand the date/time intention in this calendar query: "{query}"

The system has already extracted this date/time information:
{json.dumps(date_info, default=str)}

IMPORTANT: Today's date is {datetime.now().strftime('%Y-%m-%d')}. 

Please analyze the query and enhance the date/time understanding. Return a JSON object that improves on the existing data.
If the query mentions a time period like "last 3 days" or "past week", calculate exact dates relative to today.
Include date_range_start and date_range_end values as ISO format dates (YYYY-MM-DD).
Include an analysis field with your interpretation.

For example, if the query is "What did I do in the last week?", you might return:
{{
  "is_past": true,
  "days_range": 7,
  "specific_date": null,
  "date_range_start": "{(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}",
  "date_range_end": "{datetime.now().strftime('%Y-%m-%d')}",
  "analysis": {{
    "specific_date": false,
    "date_range": true,
    "recurring_pattern": false,
    "past_or_future": "past"
  }}
}}

Always format dates as YYYY-MM-DD strings in the date_range_start and date_range_end fields. Do not include time components.
"""
            # Trim the prompt for debug output
            debug_prompt = prompt[:100] + "..." if len(prompt) > 100 else prompt
            print(
                f"[DEBUG] Sending datetime intent prompt to LLM (trimmed): \n{debug_prompt}"
            )

            # Get completion from the LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a calendar assistant that understands date and time expressions.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )

            # Parse the JSON response
            response_text = response.choices[0].message.content
            # Trim the response for debug output
            debug_response = (
                response_text[:100] + "..."
                if len(response_text) > 100
                else response_text
            )
            print(f"[DEBUG] LLM datetime intent response (trimmed): {debug_response}")

            enhanced_date_info = json.loads(response_text)
            print(f"[DEBUG] Parsed enhanced date info: {enhanced_date_info}")

            # Convert string dates to datetime objects if present
            if enhanced_date_info.get("date_range_start") and isinstance(
                enhanced_date_info["date_range_start"], str
            ):
                try:
                    # No need to convert to datetime here, keep as string for process_intent
                    # It will be converted there when needed
                    print(
                        f"[DEBUG] Keeping date_range_start as string: {enhanced_date_info['date_range_start']}"
                    )
                except Exception as e:
                    print(f"[ERROR] Error converting date_range_start: {e}")

            if enhanced_date_info.get("date_range_end") and isinstance(
                enhanced_date_info["date_range_end"], str
            ):
                try:
                    # No need to convert to datetime here, keep as string for process_intent
                    # It will be converted there when needed
                    print(
                        f"[DEBUG] Keeping date_range_end as string: {enhanced_date_info['date_range_end']}"
                    )
                except Exception as e:
                    print(f"[ERROR] Error converting date_range_end: {e}")

            # Merge the enhanced information with the original
            # Only update fields that have changed
            for key, value in enhanced_date_info.items():
                if key in date_info and date_info[key] != value and value is not None:
                    print(f"[DEBUG] LLM enhanced {key}: {date_info[key]} -> {value}")
                    date_info[key] = value
                elif key not in date_info or date_info[key] is None:
                    print(f"[DEBUG] Adding new or updating null field: {key}={value}")
                    date_info[key] = value

            return date_info

        except Exception as e:
            print(f"[ERROR] Error in parse_datetime_intent: {e}")
            # If there's an error, return the original date_info
            return date_info

    def classify_intent(self, query: str, time_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify the intent of a natural language calendar query.

        Args:
            query: The user's natural language query
            time_info: Extracted time information from the query

        Returns:
            Dictionary with classified intent information
        """
        logger.info(f"Classifying intent for query: '{query}'")

        # Create a prompt for intent classification
        prompt = f"""
        Analyze the following calendar assistant query and determine the user's intent.
        Query: "{query}"
        
        The system has already performed date/time parsing and extracted the following temporal information:
        {json.dumps(time_info, default=str)}
        
        Consider the date context carefully in your classification. Pay special attention to:
        - Whether the query is asking about a specific date
        - Whether that date is in the past or future
        - If the query is asking about the current date/time
        - If it's asking for a range of dates or a specific day
        
        Return your analysis as a JSON object with the following fields:
        - intent_type: One of ["calendar_query", "event_creation", "time_date", "greeting", "assistant_info", "calendar_list"]
        - is_past: Boolean, whether the query refers to past events
        - days_range: Integer, the number of days to look back/forward
        - needs_calendar_data: Boolean, whether calendar data needs to be fetched
        - is_creation: Boolean, whether the user wants to create an event
        - reverse_chronological: Boolean, whether results should be shown in reverse chronological order
        - search_terms: String of relevant search terms for filtering events, or null if not applicable
        
        If the query is explicitly asking about the current date or time (e.g., "what day is it today"), make sure to classify it as "time_date" intent.
        """

        try:
            # Call the LLM to classify intent
            response = self.get_completion(prompt, model="gpt-4")

            # Parse the JSON response
            intent_data = json.loads(response)

            # Validate and ensure all required fields are present
            required_fields = [
                "intent_type",
                "is_past",
                "days_range",
                "needs_calendar_data",
                "is_creation",
                "reverse_chronological",
                "search_terms",
            ]

            for field in required_fields:
                if field not in intent_data:
                    if field == "search_terms":
                        intent_data[field] = None
                    elif field == "days_range":
                        intent_data[field] = 7  # Default to one week
                    elif field in [
                        "is_past",
                        "needs_calendar_data",
                        "is_creation",
                        "reverse_chronological",
                    ]:
                        intent_data[field] = False
                    else:
                        intent_data[field] = None

            # Make sure to properly handle date_mentioned information from time_info
            if time_info.get("date_mentioned") and time_info.get("specific_date"):
                # Override with specific date info if available
                intent_data["specific_date"] = time_info["specific_date"]

                # If the query is asking about a date but there are no calendar indicators,
                # it might be a simple date query (e.g., "what date was yesterday")
                if (
                    "what" in query.lower()
                    and ("date" in query.lower() or "day" in query.lower())
                    and not intent_data.get("needs_calendar_data", False)
                ):
                    intent_data["intent_type"] = "time_date"

            return intent_data

        except Exception as e:
            logger.error(f"Error in intent classification: {e}")
            # Return a basic default intent
            return {
                "intent_type": "calendar_query",
                "is_past": False,
                "days_range": 7,
                "search_terms": None,
                "needs_calendar_data": True,
                "is_creation": False,
                "reverse_chronological": False,
            }

    def parse_date_understanding(self, query: str, time_context: dict = None) -> dict:
        """
        Specialized method for natural language date understanding.

        Args:
            query: The user's natural language query about dates/times
            time_context: Optional context about current date/time

        Returns:
            Dictionary with structured date/time information
        """
        logger.info(f"Parsing date understanding for query: '{query}'")

        # Get current date/time
        now = datetime.now()

        # Create enhanced prompt with current time context
        prompt = f"""
You are a specialized calendar assistant focused on understanding date and time references.

CURRENT CONTEXT:
- Today's date: {now.strftime('%Y-%m-%d')}
- Current day: {now.strftime('%A')}
- Current time: {now.strftime('%H:%M')}

QUERY: "{query}"

Please extract all date and time information from this query.
Return ONLY a valid JSON object with these fields:
- is_past: boolean, true if query refers to past events
- days_range: integer, number of days being referenced
- reverse_chronological: boolean, true if results should be newest first
- specific_date: ISO format date string (YYYY-MM-DD) or null if not applicable
- date_range_start: ISO format date string or null if not applicable
- date_range_end: ISO format date string or null if not applicable
- date_mentioned: boolean, true if query explicitly mentions a date
- time_mentioned: boolean, true if query explicitly mentions a time
- relative_reference: string describing what kind of reference, or null

Be extremely precise with dates. Calculate exact dates relative to today.
For example, if today is {now.strftime('%Y-%m-%d')} and the query asks about "yesterday", 
the specific_date should be "{(now - timedelta(days=1)).strftime('%Y-%m-%d')}".
"""

        # Add extra context if provided
        if time_context:
            context_str = json.dumps(time_context, default=str)
            prompt += f"\n\nAdditional time context: {context_str}"

        try:
            # Use GPT-4 for best date understanding
            response = self.get_completion(prompt, model="gpt-4")

            # Parse JSON response
            try:
                result = json.loads(response)
                logger.info(f"Successfully parsed date information: {result}")
                return result
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse date understanding response as JSON: {e}"
                )
                logger.error(f"Response was: {response}")
                return {
                    "is_past": False,
                    "days_range": 7,
                    "error": "Failed to parse LLM response",
                }

        except Exception as e:
            logger.error(f"Error in date understanding: {e}")
            return {"is_past": False, "days_range": 7, "error": str(e)}

    def match_events_semantically(self, search_query, event_titles, top_n=3):
        """
        Use the LLM to semantically match a search query to event titles.

        Args:
            search_query: The user's search query (e.g., "daria's grad")
            event_titles: List of event titles to search through
            top_n: Number of top matches to return

        Returns:
            List of dictionaries with matched events and confidence scores
        """
        if not event_titles:
            return []

        logger.info(f"Performing semantic event matching for: '{search_query}'")

        # Format event titles for the prompt
        events_str = "\n".join(
            [f"{i+1}. {title}" for i, title in enumerate(event_titles)]
        )

        prompt = f"""
        I need to find the most semantically similar calendar events to a user's search query.
        
        User's search query: "{search_query}"
        
        Available calendar events:
        {events_str}
        
        IMPORTANT MATCHING CRITERIA:
        1. Person's names MUST match (e.g., "daria" in "daria's grad" must match "daria" in event titles)
        2. Event types should match semantically (e.g., "grad" can match "graduation" or "commencement ceremony")
        3. Possessive relationships (e.g., "daria's graduation") MUST have the correct person name match
        4. Do NOT match events belonging to different people (e.g., "daria's graduation" should not match "bahar's birthday")
        5. Require a minimum confidence of 70% for a valid match
        
        For queries using possessive form (like "daria's graduation"):
        - ONLY match events that specifically reference the same person (daria)
        - Priority should be given to events that match both the person's name AND the event type
        - Do NOT match events for different people even if the event type is similar
        
        Return a JSON array with the top {top_n} matches in this format:
        [
          {{
            "event_index": <1-based index from the list>,
            "event_title": <the matching event title>,
            "confidence": <a number from 0-100 representing match confidence>,
            "reasoning": <brief explanation of why this is a good match>
          }},
          ...
        ]
        
        If no good matches exist (confidence would be below 70), return an empty array [].
        
        IMPORTANT: Your response MUST be a valid JSON array only. Do not include any preamble or explanation text outside of the JSON.
        """

        try:
            # Use GPT-4 for better matching precision with response format parameter
            response = self.client.chat.completions.create(
                model="gpt-4" if OPENAI_AVAILABLE else "gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that returns responses in valid JSON format.",
                    },
                    {"role": "user", "content": prompt},
                ],
                # response_format={"type": "json_object"},
                temperature=0.2,
            )

            response_content = response.choices[0].message.content
            logger.info(f"Received semantic matching response from LLM")

            # Parse the JSON response
            import json
            import re

            try:
                # First try direct parsing
                matches = json.loads(response_content)

                # Check if the response is a dictionary with an array inside (common OpenAI pattern)
                if isinstance(matches, dict) and any(
                    isinstance(matches.get(k), list) for k in matches
                ):
                    # Find the first list value
                    for k, v in matches.items():
                        if isinstance(v, list):
                            matches = v
                            break

                # Ensure matches is a list
                if not isinstance(matches, list):
                    logger.warning(
                        f"Expected a list but got {type(matches)}. Trying to extract from: {response_content[:100]}..."
                    )
                    # Try to extract a JSON array using regex
                    json_match = re.search(
                        r"\[\s*\{.*\}\s*\]", response_content, re.DOTALL
                    )
                    if json_match:
                        matches = json.loads(json_match.group(0))
                    else:
                        # If that fails, wrap in an array if it's a single object
                        if isinstance(matches, dict) and "event_index" in matches:
                            matches = [matches]
                        else:
                            logger.error(
                                f"Could not extract a valid match list from the response"
                            )
                            return []

            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}")
                logger.debug(f"Response content: {response_content[:500]}...")

                # Try to extract a JSON array using regex as fallback
                json_match = re.search(r"\[\s*\{.*\}\s*\]", response_content, re.DOTALL)
                if json_match:
                    try:
                        matches = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON even with regex extraction")
                        return []
                else:
                    logger.error("No JSON array pattern found in response")
                    return []

            # Validate the response format and filter matches with confidence below 70
            valid_matches = []
            for match in matches:
                if (
                    isinstance(match, dict)
                    and "event_index" in match
                    and "confidence" in match
                    and match.get("confidence", 0) >= 70
                ):  # Only accept matches with confidence >= 70

                    # Ensure event_index is an integer
                    try:
                        match["event_index"] = (
                            int(match["event_index"]) - 1
                        )  # Convert to 0-based index

                        # Check index bounds
                        if 0 <= match["event_index"] < len(event_titles):
                            valid_matches.append(match)
                        else:
                            logger.warning(
                                f"Event index out of bounds: {match['event_index']+1}, max={len(event_titles)}"
                            )
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid event_index: {match.get('event_index')}"
                        )

            # Sort matches by confidence in descending order
            valid_matches = sorted(
                valid_matches, key=lambda x: x.get("confidence", 0), reverse=True
            )

            logger.info(
                f"Found {len(valid_matches)} valid matches out of {len(matches)} total"
            )
            return valid_matches

        except Exception as e:
            logger.error(f"Error in semantic event matching: {str(e)}")
            # More detailed error logging
            import traceback

            logger.debug(f"Error details: {traceback.format_exc()}")
            return []

    def generate_conversational_response(
        self,
        query: str,
        results: Dict[str, Any],
        conversation_context: Dict[str, Any] = None,
    ) -> str:
        """Generate a natural, conversational response based on calendar query results.

        Args:
            query: The user's original query
            results: Results dictionary from calendar processing
            conversation_context: Optional conversation context for maintaining state

        Returns:
            A natural language response explaining the results
        """
        if not self.client:
            logger.error("LLM client not initialized.")
            return "I'm having trouble generating a response right now."

        try:
            # Extract important information from results
            intent_type = results.get("intent_type", "unknown")
            events = results.get("events", [])
            is_single_day = results.get("is_single_day", False)
            specific_date_str = results.get("specific_date")
            is_find_last_occurrence = results.get("is_find_last_occurrence", False)
            is_find_next_occurrence = results.get("is_find_next_occurrence", False)
            search_terms = results.get("search_terms", "")
            error = results.get("error")

            # Create a simplified context to include in the prompt
            simplified_context = {
                "query_type": intent_type,
                "num_events": len(events),
                "is_single_day": is_single_day,
                "has_specific_date": specific_date_str is not None,
                "specific_date": specific_date_str,
                "is_find_last_occurrence": is_find_last_occurrence,
                "is_find_next_occurrence": is_find_next_occurrence,
                "search_terms": search_terms,
                "has_error": error is not None,
                "error_message": error,
            }

            # Include conversation context if provided
            conversation_state = {}
            if conversation_context:
                conversation_state = {
                    "needs_clarification": conversation_context.get(
                        "needs_clarification", False
                    ),
                    "clarification_type": conversation_context.get(
                        "pending_clarification_type"
                    ),
                    "last_query": conversation_context.get("last_query"),
                    "last_date_mentioned": conversation_context.get(
                        "last_date_mentioned"
                    ),
                }

            # Simplify events to avoid exceeding token limits
            simplified_events = []
            for event in events[:5]:  # Only include first 5 events to save tokens
                if isinstance(event, dict):
                    simplified_event = {
                        "title": event.get("title", event.get("summary", "Untitled")),
                        "start": event.get("start", ""),
                        "end": event.get("end", ""),
                        "location": event.get("location", ""),
                        "all_day": event.get("all_day", False),
                    }
                    simplified_events.append(simplified_event)

            # Create the prompt
            prompt = f"""
You are Orii, a helpful and friendly calendar assistant. You need to respond to the user's query in a natural, conversational way.

USER QUERY: "{query}"

RESULT CONTEXT:
{json.dumps(simplified_context, default=str)}

CONVERSATION CONTEXT:
{json.dumps(conversation_state, default=str)}

EVENT DATA (first 5 events only):
{json.dumps(simplified_events, default=str)}

CURRENT DATE/TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

GUIDELINES FOR RESPONSE:
1. Be concise but friendly - use natural, conversational language
2. Use contractions and casual phrasing (I'll, you're, etc.)
3. Be helpful and proactive, offering relevant suggestions based on calendar data
4. For date references, use natural time expressions like "today", "tomorrow", "this Friday", etc.
5. For past events, add context like "2 days ago" or "last week" when appropriate
6. If you need clarification, ask a specific question that guides the user
7. Avoid over-explaining technical details of calendar operations

Your response should be DIRECT - no introductory phrases like "Based on your calendar..." or "I found that...". Just the natural conversational answer.

For example, instead of "I found that your next meeting is at 3pm", just say "Your next meeting is at 3pm".
"""

            # Get completion from the LLM
            response = self.client.chat.completions.create(
                model="gpt-4" if OPENAI_AVAILABLE else "gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are Orii, a helpful and conversational calendar assistant. Be natural and friendly.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,  # Higher temperature for more natural responses
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error generating conversational response: {e}")
            return "I'm having trouble understanding that right now. Could you try asking in a different way?"


# Singleton instance for the application
_llm_client = None


def get_llm_client(provider="openai"):
    """Get or create the LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(provider=provider)
    return _llm_client
