#!/usr/bin/env python3
"""
Test script to verify retrieving events from calendars using their real names.
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
    """Main function to test calendar retrieval with actual user calendars."""
    try:
        # Set date range for next 30 days
        now = datetime.now()
        start_time = now
        end_time = now + timedelta(days=30)

        print(
            f"Testing calendar retrieval by name for date range: {start_time.date()} to {end_time.date()}\n"
        )

        # Get the list of real calendars to test based on user's actual calendars
        real_calendars = [
            "Shadi Personal",  # Primary calendar
            "Wade work",
            "jetski AI",
            "UCI",
            "Canvas",
            "Handshake",
            "Holidays in United States",
            "Remote Sensing Research Project",
        ]

        # Test each real calendar
        for cal_name in real_calendars:
            print(f"Retrieving events from '{cal_name}':")
            events = get_events_in_range(start_time, end_time, calendar_id=cal_name)
            print(f"   Found {len(events)} events")

            # Display first 3 events if any found
            if events:
                print(f"   First {min(3, len(events))} events:")
                for i, event in enumerate(events[:3], 1):
                    print(
                        f"     {i}. {event.get('summary', 'Untitled')} - {event.get('calendarName')}"
                    )

            print()

        # Test retrieving from all calendars
        print("Retrieving events from all calendars:")
        all_events = get_events_in_range(start_time, end_time)
        print(f"Found {len(all_events)} events total from all calendars")

        # Group events by calendar for display
        cal_events = {}
        for event in all_events:
            cal_name = event.get("calendarName", "Unknown")
            if cal_name not in cal_events:
                cal_events[cal_name] = 0
            cal_events[cal_name] += 1

        for cal_name, count in cal_events.items():
            print(f"   {cal_name}: {count} events")

    except Exception as e:
        print(f"Error testing calendar retrieval: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
