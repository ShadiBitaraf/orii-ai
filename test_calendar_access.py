#!/usr/bin/env python3
"""
Simple test script to verify the calendar access functionality.
"""

import sys
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Add the backend to the path
sys.path.append(".")
sys.path.append("./backend")

# Import the required modules
try:
    from backend.app.cli.calendar_service import (
        get_calendar_service,
        get_selected_calendars,
    )
    from backend.app.cli.event_retrieval import get_events_in_range
    from backend.app.utils.llm_client import get_llm_client
    from backend.app.utils.smart_date_parser import SmartDateParser
except ImportError as e:
    print(f"Error importing required modules: {e}")
    sys.exit(1)


def test_calendar_listing():
    """Test the calendar listing functionality."""
    print("\n=== Testing Calendar Listing ===")

    try:
        # Get the calendar service
        service = get_calendar_service()
        if not service:
            print("Failed to get calendar service")
            return

        # Get all selected/visible calendars
        calendars = get_selected_calendars(service)

        # Display the results
        print(f"Found {len(calendars)} visible calendars:")
        for i, cal in enumerate(calendars, 1):
            # Use 'summary' for calendar name and 'id' for calendar ID
            print(f"{i}. {cal.get('summary', 'Unnamed')} ({cal.get('id')})")
            print(f"   Primary: {cal.get('primary', False)}")
            print(f"   Access Role: {cal.get('accessRole', 'unknown')}")
            print(f"   Selected: {cal.get('selected', True)}")
            print(f"   Background Color: {cal.get('backgroundColor', 'default')}")
            print(f"   Time Zone: {cal.get('timeZone', 'default')}")
            print()

    except Exception as e:
        print(f"Error in calendar listing test: {e}")


def test_event_retrieval():
    """Test the event retrieval functionality."""
    print("\n=== Testing Event Retrieval ===")

    try:
        # Create a date range for the test
        now = datetime.now()
        start_time = now
        end_time = now + timedelta(days=7)

        # Get events from all calendars
        print("Fetching events from all calendars...")
        all_events = get_events_in_range(start_time, end_time)
        print(f"Found {len(all_events)} total events across all calendars\n")

        # Get the calendar service to list available calendars
        service = get_calendar_service()
        if not service:
            print("Failed to get calendar service")
            return

        calendars = get_selected_calendars(service)

        # Test with a specific calendar if available
        if calendars:
            # Try with the first calendar
            cal = calendars[0]
            cal_id = cal.get("id")
            cal_name = cal.get("summary", "Unnamed")

            print(f"Fetching events from specific calendar: {cal_name}...")
            cal_events = get_events_in_range(start_time, end_time, calendar_id=cal_id)
            print(f"Found {len(cal_events)} events in calendar '{cal_name}'\n")

            # Try searching with a name instead of ID
            if len(calendars) > 1:
                cal2 = calendars[1]
                cal2_name = cal2.get("summary", "Unnamed")

                print(f"Fetching events by calendar name: {cal2_name}...")
                name_events = get_events_in_range(
                    start_time, end_time, calendar_id=cal2_name
                )
                print(
                    f"Found {len(name_events)} events searching by calendar name '{cal2_name}'\n"
                )

            # Try a non-existent calendar
            print("Testing with a non-existent calendar name...")
            fake_events = get_events_in_range(
                start_time, end_time, calendar_id="fake_calendar_name"
            )
            print(f"Found {len(fake_events)} events with non-existent calendar name\n")

    except Exception as e:
        print(f"Error in event retrieval test: {e}")


def test_parser_with_calendar():
    """Test the smart date parser with calendar specification."""
    print("\n=== Testing Parser with Calendar Specification ===")

    try:
        # Initialize the parser
        parser = SmartDateParser()

        # Test queries with calendar specification
        test_queries = [
            "what events do I have tomorrow in my primary calendar?",
            "meetings next week in my work calendar",
            "show me events on Friday in my personal calendar",
            "what's happening today in all my calendars?",
        ]

        for query in test_queries:
            print(f"\nParsing query: '{query}'")
            time_info = parser.parse_with_context(query)
            print(f"Time info: {time_info}")

            # Use regex to extract calendar name (this would normally be done by intent detection)
            import re

            calendar_match = re.search(r"in\s+my\s+(\w+)\s+calendar", query)
            specified_calendar = calendar_match.group(1) if calendar_match else None

            if specified_calendar:
                print(f"Extracted calendar name: '{specified_calendar}'")

                # Get time range
                now = datetime.now()
                start_time = time_info.get("specific_date", now)
                end_time = (
                    start_time.replace(hour=23, minute=59, second=59)
                    if start_time
                    else (now + timedelta(days=1))
                )

                # Test retrieving events
                print(f"Fetching events for calendar '{specified_calendar}'...")
                events = get_events_in_range(
                    start_time, end_time, calendar_id=specified_calendar
                )
                print(f"Found {len(events)} events")

    except Exception as e:
        print(f"Error in parser test: {e}")


if __name__ == "__main__":
    print("Testing Calendar Access Functionality")
    print("====================================\n")

    test_calendar_listing()
    test_event_retrieval()
    test_parser_with_calendar()

    print("\nTests completed.")
