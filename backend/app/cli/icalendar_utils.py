"""
iCalendar utilities module that re-exports from utils/icalendar_utils.py.
This avoids duplicate implementations and circular imports.
"""

# Re-export all functions and constants from icalendar_utils
from ..utils.icalendar_utils import (
    create_calendar,
    create_event_from_details,
    event_to_dict,
    dict_to_google_event,
    google_event_to_dict,
    generate_ics_file,
    parse_ics_file,
    DEFAULT_TIMEZONE,
    DEFAULT_PRODID,
)

# Export all symbols for star imports
__all__ = [
    "create_calendar",
    "create_event_from_details",
    "event_to_dict",
    "dict_to_google_event",
    "google_event_to_dict",
    "generate_ics_file",
    "parse_ics_file",
    "DEFAULT_TIMEZONE",
    "DEFAULT_PRODID",
]
