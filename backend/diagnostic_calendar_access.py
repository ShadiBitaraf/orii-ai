#!/usr/bin/env python3
"""
Diagnostic script to understand calendar access discrepancies.
"""

import sys
import logging
import json

logging.basicConfig(level=logging.INFO)

# Add the path
sys.path.append(".")

# Import the required modules
from app.cli.calendar_service import (
    get_calendar_service,
    get_selected_calendars,
    get_calendar_list,
)


def main():
    """Compare different methods of accessing calendars."""
    try:
        # Get the calendar service
        service = get_calendar_service()
        if not service:
            print("Failed to get calendar service")
            return

        # Method 1: Direct API call (as used in all_calendar_info.py)
        print("\n=== Method 1: Direct API Call ===")
        calendar_list = service.calendarList().list().execute()
        direct_items = calendar_list.get("items", [])
        print(f"Found {len(direct_items)} calendars using direct API call")
        print("Calendar names:")
        for cal in direct_items:
            name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
            print(f"  - {name} (ID: {cal.get('id')})")

        # Method 2: get_calendar_list function
        print("\n=== Method 2: get_calendar_list ===")
        all_calendars = get_calendar_list(service)
        print(f"Found {len(all_calendars)} calendars using get_calendar_list")
        print("Calendar names:")
        for cal in all_calendars:
            name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
            print(f"  - {name} (ID: {cal.get('id')})")

        # Method 3: get_selected_calendars function
        print("\n=== Method 3: get_selected_calendars ===")
        selected_calendars = get_selected_calendars(service)
        print(f"Found {len(selected_calendars)} calendars using get_selected_calendars")
        print("Calendar names:")
        for cal in selected_calendars:
            name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
            print(f"  - {name} (ID: {cal.get('id')})")

        # Compare filtering criteria
        print("\n=== Filtering Analysis ===")
        if len(direct_items) != len(selected_calendars):
            print("Some calendars are being filtered out. Checking why...")

            # Check which calendars are missing from selected_calendars
            selected_ids = [cal.get("id") for cal in selected_calendars]
            filtered_out = [
                cal for cal in direct_items if cal.get("id") not in selected_ids
            ]

            if filtered_out:
                print(f"These {len(filtered_out)} calendars were filtered out:")
                for cal in filtered_out:
                    name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
                    print(f"  - {name} (ID: {cal.get('id')})")
                    print(f"    Selected: {cal.get('selected', True)}")
                    print(f"    Hidden: {cal.get('hidden', False)}")
                    print(f"    Access Role: {cal.get('accessRole', 'unknown')}")

            # Check API caching
            cached_calendar_list = get_calendar_list(service)
            print(
                f"\nAPI Caching Test: Second call to get_calendar_list returned {len(cached_calendar_list)} calendars"
            )

        # Check IDs to see if they look valid
        print("\n=== Calendar ID Analysis ===")
        for cal in selected_calendars:
            cal_id = cal.get("id")
            cal_name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
            print(f"Calendar: {cal_name}")
            print(f"  ID: {cal_id}")

            # Test if this ID is valid by making a direct API call
            try:
                calendar_info = service.calendars().get(calendarId=cal_id).execute()
                print(f"  ✓ ID is valid")
            except Exception as e:
                print(f"  ✗ ID is invalid: {str(e)}")

    except Exception as e:
        print(f"Error in diagnostic: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
