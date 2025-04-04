"""
LLM client for the application.

This module provides a client for LLM services.
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)


class LLMClient:
    """Client for LLM services."""

    def __init__(self):
        """Initialize the LLM client."""
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.initialized = False

        if self.api_key:
            try:
                import openai

                openai.api_key = self.api_key
                self.client = openai.OpenAI(api_key=self.api_key)
                self.initialized = True
            except (ImportError, Exception) as e:
                logger.warning(f"Error initializing OpenAI client: {e}")
                # Create a stub client attribute to avoid AttributeError
                self.client = None
        else:
            logger.warning(
                "OpenAI API key not found. LLM functionality will be limited."
            )
            # Create a stub client attribute to avoid AttributeError
            self.client = None

    def extract_event_details(
        self, query: str, time_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract event details from a query.

        Args:
            query: The user query
            time_info: Time information extracted from the query

        Returns:
            Dictionary with event details
        """
        # Simple stub implementation for testing
        event_details = {
            "summary": f"Event from query: {query[:30]}...",
            "description": f"Extracted from query on {datetime.now().isoformat()}",
            "start_time": time_info.get("specific_date", datetime.now()),
            "end_time": time_info.get("specific_date", datetime.now()),
            "is_all_day": False,
        }

        return event_details

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
        # Simple stub implementation for testing
        if "error" in results:
            return f"I'm sorry, I encountered an error: {results.get('error')}"

        intent_type = results.get("intent_type")

        if intent_type == "calendar_query":
            events = results.get("events", [])

            if not events:
                return "You don't have any events scheduled for that time period."

            if len(events) == 1:
                event = events[0]
                return (
                    f"I found one event: {event.get('title')} at {event.get('start')}."
                )
            else:
                return f"I found {len(events)} events for that time period."

        elif intent_type == "time_date":
            if "date" in results:
                return f"It's {results['date']}."

        # Default response
        return "I'm not sure how to respond to that. Could you please clarify?"


_llm_client_instance = None


def get_llm_client():
    """Get a singleton instance of the LLM client.

    Returns:
        LLM client instance
    """
    global _llm_client_instance

    if _llm_client_instance is None:
        logger.info("LLM client initialized for SmartDateParser")
        _llm_client_instance = LLMClient()

    return _llm_client_instance
