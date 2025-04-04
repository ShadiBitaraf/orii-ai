"""
CLI package for the application.
"""

from .cli import main
from .commands import CommandHandlers
from .calendar_service import get_calendar_service, get_events, get_event
from .cache import get_cached_data, set_cached_data
from .llm_service import LLMService
from .metrics import Metrics
from .time_manager import (
    parse_time_range,
    parse_natural_language_datetime,
    format_datetime_range,
)

__all__ = [
    "main",
    "CommandHandlers",
    "get_calendar_service",
    "get_events",
    "get_event",
    "get_cached_data",
    "set_cached_data",
    "LLMService",
    "Metrics",
    "parse_time_range",
    "parse_natural_language_datetime",
    "format_datetime_range",
]
