"""
Example script demonstrating iCalendar functionality.

This script shows how to use the iCalendar utilities for common calendar operations.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import pytz

# Add parent directory to path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from cli.calendar_service import (
    get_calendar_service,
    get_events,
    export_events_to_ics,
    import_events_from_ics,
)
from cli.event_management import (
    create_event,
    update_event,
    delete_event,
    format_event_text,
)
from cli.icalendar_utils import (
    create_calendar,
    create_event_from_details,
    generate_ics_file,
    parse_ics_file,
    dict_to_google_event,
    google_event_to_dict,
)


def export_calendar_example(service, output_file="calendar_export.ics"):
    """
    Example: Export calendar events to an iCalendar file.

    Args:
        service: Google Calendar service
        output_file: Output .ics filename
    """
    print(f"\n=== Exporting Calendar to {output_file} ===")

    # Get current date and time
    now = datetime.now(pytz.UTC)

    # Set time range for the next 30 days
    time_min = now.isoformat()
    time_max = (now + timedelta(days=30)).isoformat()

    # Export events
    result = export_events_to_ics(
        service, time_min=time_min, time_max=time_max, filename=output_file
    )

    if result:
        print(f"✅ Calendar exported successfully to {result}")

        # Read the file back to verify
        events = parse_ics_file(result)
        print(f"Found {len(events)} events in the exported file")

        # Print some example events
        for i, event in enumerate(events[:3]):
            print(f"\n🗓️ Event {i+1}: {event.get('summary')}")
            if event.get("is_all_day"):
                date_str = event.get("start_date").strftime("%Y-%m-%d")
                print(f"All-day on {date_str}")
            else:
                start_str = event.get("start_time").strftime("%Y-%m-%d %H:%M")
                print(f"Starts at {start_str}")
    else:
        print("❌ Failed to export calendar")


def create_event_example(service):
    """
    Example: Create an event using iCalendar format.

    Args:
        service: Google Calendar service
    """
    print("\n=== Creating a New Event ===")

    # Get current date and time
    now = datetime.now(pytz.UTC)

    # Define an event starting tomorrow at 10 AM, lasting 1 hour
    tomorrow = now.date() + timedelta(days=1)
    start_time = datetime.combine(tomorrow, datetime.min.time().replace(hour=10))
    end_time = start_time + timedelta(hours=1)

    # Build event details
    event_details = {
        "summary": "iCalendar Test Meeting",
        "description": "This event was created using iCalendar protocol",
        "location": "Conference Room A",
        "start_time": start_time,
        "end_time": end_time,
        "attendees": ["test@example.com"],
        "reminders": [{"minutes": 15}],
    }

    # Create the event
    created_event = create_event(service, event_details)

    if created_event:
        print("✅ Event created successfully!")
        print(format_event_text(created_event))
        return created_event
    else:
        print("❌ Failed to create event")
        return None


def update_event_example(service, event):
    """
    Example: Update an existing event.

    Args:
        service: Google Calendar service
        event: Event to update
    """
    if not event:
        print("❌ No event to update")
        return

    print("\n=== Updating Event ===")

    # Make some changes to the event
    updates = {
        "summary": f"{event['summary']} (Updated)",
        "description": f"{event.get('description', '')} - This event was updated using iCalendar protocol",
        "location": "Conference Room B",
    }

    # Update the event
    updated_event = update_event(service, event["uid"], updates)

    if updated_event:
        print("✅ Event updated successfully!")
        print(format_event_text(updated_event))
        return updated_event
    else:
        print("❌ Failed to update event")
        return None


def create_ical_file_example(output_file="manual_calendar.ics"):
    """
    Example: Manually create an iCalendar file with events.

    Args:
        output_file: Output .ics filename
    """
    print(f"\n=== Creating Manual iCalendar File: {output_file} ===")

    # Create a new calendar
    cal = create_calendar(
        name="My Manual Calendar", description="Calendar created manually"
    )

    # Get current date and time
    now = datetime.now(pytz.UTC)
    today = now.date()

    # Create some events
    events = []

    # Event 1: All-day event
    event1 = {
        "summary": "All-Day Conference",
        "description": "Annual conference on calendar technologies",
        "location": "Convention Center",
        "is_all_day": True,
        "start_date": today + timedelta(days=5),
        "end_date": today + timedelta(days=7),
    }
    events.append(event1)

    # Event 2: Regular timed event
    event2 = {
        "summary": "Project Planning Meeting",
        "description": "Discuss Q3 project timelines",
        "location": "Virtual Meeting",
        "start_time": datetime.combine(
            today + timedelta(days=2), datetime.min.time().replace(hour=14)
        ),
        "end_time": datetime.combine(
            today + timedelta(days=2), datetime.min.time().replace(hour=15, minute=30)
        ),
        "attendees": ["colleague1@example.com", "colleague2@example.com"],
        "reminders": [{"minutes": 10}, {"minutes": 30}],
    }
    events.append(event2)

    # Event 3: Recurring event
    event3 = {
        "summary": "Weekly Team Standup",
        "description": "Weekly team status update",
        "location": "Meeting Room 3",
        "start_time": datetime.combine(
            today + timedelta(days=(7 - today.weekday()) % 7),
            datetime.min.time().replace(hour=9, minute=30),
        ),
        "end_time": datetime.combine(
            today + timedelta(days=(7 - today.weekday()) % 7),
            datetime.min.time().replace(hour=10),
        ),
        "recurrence": "FREQ=WEEKLY;BYDAY=MO;COUNT=10",  # Every Monday for 10 occurrences
    }
    events.append(event3)

    # Generate the iCalendar file
    result = generate_ics_file(events, filename=output_file)

    if result:
        print(f"✅ iCalendar file created successfully: {result}")

        # Read it back to verify
        parsed_events = parse_ics_file(result)
        print(f"Verified {len(parsed_events)} events in the file")
    else:
        print("❌ Failed to create iCalendar file")


def import_calendar_example(service, input_file="manual_calendar.ics"):
    """
    Example: Import events from an iCalendar file.

    Args:
        service: Google Calendar service
        input_file: Input .ics filename
    """
    print(f"\n=== Importing Calendar from {input_file} ===")

    if not os.path.exists(input_file):
        print(f"❌ File does not exist: {input_file}")
        return

    # Import the events
    result = import_events_from_ics(service, input_file)

    if result:
        print(f"✅ Calendar imported successfully!")
        print(f"Total events: {result['total']}")
        print(f"Successfully imported: {result['success']}")
        print(f"Errors: {result['errors']}")

        if result["errors"] > 0:
            for error in result["error_details"]:
                print(f"Error importing {error['event']}: {error['error']}")
    else:
        print("❌ Failed to import calendar")


def delete_event_example(service, event):
    """
    Example: Delete an event.

    Args:
        service: Google Calendar service
        event: Event to delete
    """
    if not event:
        print("❌ No event to delete")
        return

    print("\n=== Deleting Event ===")

    # Delete the event
    result = delete_event(service, event["uid"])

    if result:
        print(f"✅ Event '{event['summary']}' deleted successfully")
    else:
        print("❌ Failed to delete event")


def main():
    """Run iCalendar examples."""
    parser = argparse.ArgumentParser(description="iCalendar examples")
    parser.add_argument(
        "--export", action="store_true", help="Export calendar to .ics file"
    )
    parser.add_argument("--create", action="store_true", help="Create a new event")
    parser.add_argument(
        "--manual", action="store_true", help="Create a manual .ics file"
    )
    parser.add_argument(
        "--import", dest="import_ics", action="store_true", help="Import a .ics file"
    )
    parser.add_argument("--all", action="store_true", help="Run all examples")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    # Initialize Google Calendar service
    try:
        service = get_calendar_service()
        print("✅ Connected to Google Calendar API")
    except Exception as e:
        print(f"❌ Failed to connect to Google Calendar API: {e}")
        return

    # Set file paths
    export_file = "exported_calendar.ics"
    manual_file = "manual_calendar.ics"

    # Run examples
    if args.export or args.all:
        export_calendar_example(service, export_file)

    if args.create or args.all:
        event = create_event_example(service)
        if event and args.all:
            updated_event = update_event_example(service, event)
            if args.all:
                delete_event_example(service, updated_event or event)

    if args.manual or args.all:
        create_ical_file_example(manual_file)

    if args.import_ics or args.all:
        if os.path.exists(manual_file):
            import_calendar_example(service, manual_file)
        else:
            print(f"❌ Manual calendar file not found: {manual_file}")


if __name__ == "__main__":
    main()
