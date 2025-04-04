# iCalendar Integration for Orii Calendar Assistant

This document explains the iCalendar (RFC 5545) integration in the Orii Calendar Assistant, which standardizes calendar operations and improves interoperability with various calendar systems.

## Overview

The iCalendar protocol implementation provides:

1. Standardized event format across different calendar systems
2. Advanced support for recurring events
3. Better handling of time zones and all-day events
4. Simplified import/export capabilities for calendar data
5. Improved interoperability with other calendar systems

## Key Components

The iCalendar integration consists of several modules:

- **icalendar_utils.py**: Core utilities for working with iCalendar format
- **calendar_service.py**: Google Calendar API integration with iCalendar support
- **event_management.py**: Event operations using standardized iCalendar format
- **cache.py**: Caching system to reduce API calls
- **monitoring.py**: Performance tracking for calendar operations

## Usage Examples

### Creating Events

```python
from cli.calendar_service import get_calendar_service
from cli.event_management import create_event

# Initialize service
service = get_calendar_service()

# Create an event using standardized format
event_details = {
    'summary': 'Team Meeting',
    'description': 'Weekly team sync',
    'location': 'Conference Room A',
    'start_time': datetime(2023, 6, 15, 10, 0),
    'end_time': datetime(2023, 6, 15, 11, 0),
    'attendees': ['team@example.com'],
    'reminders': [{'minutes': 15}]
}

# Create the event
created_event = create_event(service, event_details)
```

### Working with iCalendar Files

```python
from cli.icalendar_utils import create_calendar, create_event_from_details, generate_ics_file

# Create a calendar
cal = create_calendar(name="My Calendar", timezone="America/New_York")

# Create events and add to a list
events = [
    {
        'summary': 'All-Day Conference',
        'is_all_day': True,
        'start_date': date(2023, 7, 1),
        'end_date': date(2023, 7, 3)
    },
    {
        'summary': 'Recurring Meeting',
        'start_time': datetime(2023, 6, 20, 14, 0),
        'end_time': datetime(2023, 6, 20, 15, 0),
        'recurrence': 'FREQ=WEEKLY;BYDAY=TU'  # Every Tuesday
    }
]

# Generate an .ics file
ics_file = generate_ics_file(events, filename="my_calendar.ics")
```

### Importing and Exporting Calendars

```python
from cli.calendar_service import export_events_to_ics, import_events_from_ics

# Export calendar events to .ics file
export_events_to_ics(
    service,
    calendar_id="primary",
    time_min="2023-06-01T00:00:00Z",
    time_max="2023-06-30T23:59:59Z",
    filename="june_calendar.ics"
)

# Import events from .ics file
result = import_events_from_ics(service, "external_calendar.ics")
```

## Full Example

See the `examples/icalendar_example.py` script for a complete demonstration of the iCalendar functionality.

To run the example:

```
cd backend
python -m app.cli.examples.icalendar_example --all
```

Or run specific examples:

```
python -m app.cli.examples.icalendar_example --create  # Create a test event
python -m app.cli.examples.icalendar_example --export  # Export to .ics file
python -m app.cli.examples.icalendar_example --manual  # Manually create .ics file
python -m app.cli.examples.icalendar_example --import  # Import from .ics file
```

## Benefits of iCalendar Integration

1. **Standardization**: Consistent event format regardless of calendar provider
2. **Interoperability**: Seamless integration with other calendar systems
3. **Portability**: Easy import/export of calendar data
4. **Rich Event Support**: Advanced handling of recurrence, time zones, and event properties
5. **Simplified Development**: Clean abstractions for calendar operations

## References

- [RFC 5545: Internet Calendaring and Scheduling Core Object Specification](https://tools.ietf.org/html/rfc5545)
- [iCalendar Python Package](https://icalendar.readthedocs.io/)
- [Google Calendar API Documentation](https://developers.google.com/calendar)
