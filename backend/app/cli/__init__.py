"""
CLI package for the application.
"""

from .cli import main
from .commands import CommandHandlers
from ..core.calendar.calendar_service import get_calendar_service, get_events, get_event
from ..utils.cache_utils import get_cached_data, set_cached_data
from ..core.llm.llm_service import LLMService
from ..utils.metrics_utils import Metrics
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
