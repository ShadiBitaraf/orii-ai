"""
PostHog integration configuration for ORII.
Handles user behavior tracking and analytics.
"""

import os
from posthog import Posthog
from typing import Dict, Any, Optional
import time


class PosthogTracker:
    """Helper class for tracking user behavior with PostHog"""

    def __init__(self):
        """Initialize the PostHog tracker"""
        self.client = Posthog(
            project_api_key=os.getenv("POSTHOG_API_KEY"),
            host=os.getenv("POSTHOG_HOST", "https://app.posthog.com"),
        )

    def track_event(
        self, user_id: str, event_name: str, properties: Optional[Dict[str, Any]] = None
    ):
        """
        Track a user event

        Args:
            user_id: Unique identifier for the user
            event_name: Name of the event to track
            properties: Additional properties for the event
        """
        try:
            self.client.capture(
                distinct_id=user_id, event=event_name, properties=properties or {}
            )
        except Exception as e:
            print(f"Error tracking event: {str(e)}")


class SessionTracker:
    """Helper class for tracking user sessions"""

    def __init__(self, posthog_tracker: PosthogTracker):
        """
        Initialize the session tracker

        Args:
            posthog_tracker: PostHog tracker instance
        """
        self.tracker = posthog_tracker
        self.active_sessions: Dict[str, float] = {}

    def start_session(self, user_id: str, session_type: str):
        """
        Start tracking a user session

        Args:
            user_id: Unique identifier for the user
            session_type: Type of session (e.g., 'cli', 'extension')
        """
        self.active_sessions[user_id] = time.time()
        self.tracker.track_event(
            user_id=user_id,
            event_name="session_started",
            properties={"session_type": session_type},
        )

    def end_session(self, user_id: str, session_type: str):
        """
        End tracking a user session

        Args:
            user_id: Unique identifier for the user
            session_type: Type of session (e.g., 'cli', 'extension')
        """
        if user_id in self.active_sessions:
            duration = time.time() - self.active_sessions[user_id]
            self.tracker.track_event(
                user_id=user_id,
                event_name="session_ended",
                properties={"session_type": session_type, "duration": duration},
            )
            del self.active_sessions[user_id]


class QueryTracker:
    """Helper class for tracking user queries"""

    def __init__(self, posthog_tracker: PosthogTracker):
        """
        Initialize the query tracker

        Args:
            posthog_tracker: PostHog tracker instance
        """
        self.tracker = posthog_tracker

    def track_query(
        self,
        user_id: str,
        query_text: str,
        query_type: str,
        response: Optional[str] = None,
        duration: Optional[float] = None,
        success: bool = True,
    ):
        """
        Track a user query

        Args:
            user_id: Unique identifier for the user
            query_text: The query text
            query_type: Type of query (e.g., 'calendar_query', 'event_creation')
            response: Optional response text
            duration: Optional query duration
            success: Whether the query was successful
        """
        properties = {
            "query_type": query_type,
            "query_length": len(query_text),
            "success": success,
        }

        if response:
            properties["response_length"] = len(response)
        if duration:
            properties["duration"] = duration

        self.tracker.track_event(
            user_id=user_id, event_name="user_query", properties=properties
        )
