"""
Monitoring and analytics module for the application.
"""

from .posthog import initialize_posthog, capture_event, identify_user

__all__ = ["initialize_posthog", "capture_event", "identify_user"]
