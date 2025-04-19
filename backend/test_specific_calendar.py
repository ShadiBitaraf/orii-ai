#!/usr/bin/env python3
"""
Test retrieving events from specific calendars by name.
"""

import sys
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

# Add the path
sys.path.append(".")

# Import the required modules
from app.cli.event_retrieval import get_events_in_range


def main():
    """Test retrieving events from specific calendars."""
    # Set date range for next 30 days
    now = datetime.now()
    start_time = now
    end_time = now + timedelta(days=30)

    print(
        f"Testing calendar retrieval for date range: {start_time.date()} to {end_time.date()}\n"
    )

    # Test with jetski AI calendar
    test_calendar_name = "jetski AI"
    print(f"Testing retrieval from '{test_calendar_name}':")
    events = get_events_in_range(start_time, end_time, calendar_id=test_calendar_name)

    print(f"Found {len(events)} events in {test_calendar_name}")
    if events:
        print("\nFirst few events:")
        for i, event in enumerate(events[:3], 1):
            print(
                f"{i}. {event.get('summary', 'Untitled')} - {event.get('calendarName')}"
            )
            print(f"   Start: {event.get('start', {}).get('dateTime', 'N/A')}")
            print(f"   Calendar ID: {event.get('calendarId')}")

    # Test retrieving from all calendars
    print("\nRetrieving from all calendars:")
    all_events = get_events_in_range(start_time, end_time)

    # Group events by calendar
    events_by_calendar = {}
    for event in all_events:
        cal_name = event.get("calendarName", "Unknown")
        if cal_name not in events_by_calendar:
            events_by_calendar[cal_name] = []
        events_by_calendar[cal_name].append(event)

    print(f"Found events from {len(events_by_calendar)} calendars:")
    for cal_name, cal_events in events_by_calendar.items():
        print(f"- {cal_name}: {len(cal_events)} events")


if __name__ == "__main__":
    main()
