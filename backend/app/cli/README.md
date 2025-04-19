# Calendar Assistant CLI Components

This directory contains the core functionality for the calendar assistant CLI, including calendar access, event retrieval, and various utilities.

## Key Components

- **calendar_service.py**: Core service for accessing Google Calendar API
- **event_retrieval.py**: Functions for retrieving and querying calendar events
- **calendar_id_helper.py**: Utilities for safely resolving calendar IDs
- **intent_detection.py**: User intent classification and processing
- **icalendar_utils.py**: Utilities for working with iCalendar format

## Calendar ID Resolution

When a user specifies a calendar using a descriptive name like "work calendar" or "personal calendar", we need to map that to an actual Google Calendar ID. The `calendar_id_helper.py` module provides utilities for safely resolving these descriptive names to valid calendar IDs.

### Common Issues

One common issue was trying to use descriptive names like "work" directly as calendar IDs in Google Calendar API calls, resulting in 404 errors:

```
ERROR: Error fetching events from calendar work: <HttpError 404 when requesting
https://www.googleapis.com/calendar/v3/calendars/work/events?... returned "Not Found">
```

### Best Practices

When working with calendar IDs:

1. **Never use user-provided calendar names directly** as calendar IDs in API calls
2. **Always resolve calendar names** to valid IDs using `resolve_calendar_id()`
3. Use `find_matching_calendars()` to find calendars matching a search term

Example:

```python
from .calendar_id_helper import resolve_calendar_id

# Safe way to resolve user-provided calendar name to a valid ID
calendar_id = resolve_calendar_id(service, "work")
if calendar_id:
    # Now use the resolved ID with the API
    events = service.events().list(calendarId=calendar_id, ...).execute()
```

## Testing

Use the provided test scripts to verify calendar functionality:

- **test_calendar_access.py**: Tests basic calendar access
- **test_calendar_id_fix.py**: Verifies the calendar ID resolution fix
- **diagnostic_calendar_access.py**: Diagnoses calendar access issues

## Debugging Tips

If you encounter calendar access issues:

1. Check the logs for 404 errors
2. Run `diagnostic_calendar_access.py` to check available calendars
3. Verify that calendar resolution is working with `test_calendar_id_fix.py`
4. Ensure you're not using descriptive names directly as calendar IDs
