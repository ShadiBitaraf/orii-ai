"""
PostHog client implementation for analytics.
"""

import os
import posthog
from typing import Dict, Any, Optional
from ...utils.logger import get_logger

logger = get_logger("app.monitoring.posthog")

# PostHog client instance
_posthog_client = None


def initialize_posthog():
    """
    Initialize the PostHog client with API key from environment.

    Returns:
        bool: True if initialization was successful, False otherwise
    """
    global _posthog_client

    # Don't initialize if already initialized
    if _posthog_client is not None:
        return True

    try:
        api_key = os.environ.get("POSTHOG_API_KEY")
        if not api_key:
            logger.warning("PostHog API key not found in environment variables")
            return False

        # Initialize the client - by default uses US instance
        posthog.api_key = api_key
        _posthog_client = posthog

        # Set custom host if provided
        host = os.environ.get("POSTHOG_HOST")
        if host:
            posthog.host = host

        logger.info("PostHog client initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing PostHog client: {e}")
        return False


def capture_event(
    event_name: str,
    properties: Optional[Dict[str, Any]] = None,
    distinct_id: Optional[str] = None,
):
    """
    Capture an event in PostHog.

    Args:
        event_name: Name of the event
        properties: Optional event properties
        distinct_id: Optional user ID to associate with the event

    Returns:
        bool: True if the event was sent successfully, False otherwise
    """
    # Initialize if not already initialized
    if _posthog_client is None and not initialize_posthog():
        return False

    try:
        if distinct_id is None:
            distinct_id = "anonymous"

        # Send the event
        _posthog_client.capture(
            distinct_id=distinct_id, event=event_name, properties=properties or {}
        )
        return True
    except Exception as e:
        logger.error(f"Error capturing event {event_name}: {e}")
        return False


def identify_user(user_id: str, properties: Optional[Dict[str, Any]] = None):
    """
    Identify a user in PostHog.

    Args:
        user_id: The user ID
        properties: Optional user properties

    Returns:
        bool: True if the identify call was sent successfully, False otherwise
    """
    # Initialize if not already initialized
    if _posthog_client is None and not initialize_posthog():
        return False

    try:
        # Send the identify call
        _posthog_client.identify(distinct_id=user_id, properties=properties or {})
        return True
    except Exception as e:
        logger.error(f"Error identifying user {user_id}: {e}")
        return False
