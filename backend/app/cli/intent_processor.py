"""
Intent processor module that re-exports from core/intent/intent_processor.py.
This avoids circular imports.
"""

# Re-export all functions and constants from core/intent/intent_processor
from ..core.intent.intent_processor import (
    process_intent,
    process_search_events_intent,
    process_create_event_intent,
    process_update_event_intent,
    process_delete_event_intent,
    process_get_event_details_intent,
    process_list_calendars_intent,
    process_time_date_intent,
    process_greeting_intent,
    process_calendar_access_query_intent,
)

# Export all symbols for star imports
__all__ = [
    "process_intent",
    "process_search_events_intent",
    "process_create_event_intent",
    "process_update_event_intent",
    "process_delete_event_intent",
    "process_get_event_details_intent",
    "process_list_calendars_intent",
    "process_time_date_intent",
    "process_greeting_intent",
    "process_calendar_access_query_intent",
]
