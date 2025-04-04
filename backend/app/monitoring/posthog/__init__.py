"""
PostHog integration module for analytics.
"""

from .client import initialize_posthog, capture_event, identify_user

__all__ = ["initialize_posthog", "capture_event", "identify_user"]
