"""
Time manager module that re-exports from core/time/time_manager.py.
This avoids circular imports.
"""

# Re-export all functions and constants from core/time/time_manager
from ..core.time.time_manager import (
    parse_time_range,
    parse_natural_language_datetime,
    format_datetime_range,
    convert_to_timezone,
    extract_date_range_from_query,
    is_weekend,
    get_next_workday,
    get_relative_date,
    is_same_day,
    format_duration,
    DEFAULT_TIMEZONE,
    DEFAULT_DATE_FORMAT,
    DEFAULT_TIME_FORMAT,
    DEFAULT_DATETIME_FORMAT,
)

# Export all symbols for star imports
__all__ = [
    "parse_time_range",
    "parse_natural_language_datetime",
    "format_datetime_range",
    "convert_to_timezone",
    "extract_date_range_from_query",
    "is_weekend",
    "get_next_workday",
    "get_relative_date",
    "is_same_day",
    "format_duration",
    "DEFAULT_TIMEZONE",
    "DEFAULT_DATE_FORMAT",
    "DEFAULT_TIME_FORMAT",
    "DEFAULT_DATETIME_FORMAT",
]
