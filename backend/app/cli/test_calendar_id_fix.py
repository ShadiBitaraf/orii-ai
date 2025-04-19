#!/usr/bin/env python3
"""
Test script to verify the calendar ID resolution fix.
"""

import sys
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("calendar_fix_test")

# Add the app path
sys.path.append(".")

# Import the relevant modules
from app.cli.calendar_service import get_calendar_service, get_selected_calendars
from app.cli.event_retrieval import get_events_in_range
from app.cli.calendar_id_helper import resolve_calendar_id, find_matching_calendars


def test_calendar_id_resolution():
    """Test that calendar ID resolution works correctly now."""
    logger.info("=== Testing Calendar ID Resolution Fix ===")

    # Get calendar service
    service = get_calendar_service()
    if not service:
        logger.error("Failed to get calendar service")
        return False

    # List all available calendars
    calendars = get_selected_calendars(service)
    if not calendars:
        logger.error("No calendars available")
        return False

    logger.info(f"Available calendars ({len(calendars)}):")
    for cal in calendars:
        cal_id = cal.get("id")
        cal_name = cal.get("summaryOverride", cal.get("summary", "Unknown"))
        logger.info(f"  - {cal_name} (ID: {cal_id})")

    # Test cases to try
    test_cases = [
        "work",
        "personal",
        "family",
        # Include a calendar name substring that should match an actual calendar
        calendars[0].get("summary", "Unknown")[:4] if calendars else "test",
    ]

    success = True

    # Set up a date range for testing
    now = datetime.now()
    start_time = now
    end_time = now + timedelta(days=7)

    for test_term in test_cases:
        logger.info(f"\nTesting resolution for: '{test_term}'")

        # 1. First try direct resolution
        resolved_id = resolve_calendar_id(service, test_term)
        if resolved_id:
            logger.info(
                f"✓ Successfully resolved '{test_term}' to calendar ID: {resolved_id}"
            )
        else:
            logger.warning(f"✗ Could not resolve '{test_term}' to a valid calendar ID")
            success = False

        # 2. Now try getting events using this term
        try:
            events = get_events_in_range(start_time, end_time, calendar_id=test_term)
            logger.info(
                f"✓ Successfully retrieved {len(events)} events using term '{test_term}'"
            )
        except Exception as e:
            logger.error(f"✗ Failed to retrieve events with term '{test_term}': {e}")
            success = False

    return success


if __name__ == "__main__":
    if test_calendar_id_resolution():
        logger.info("\n✅ Calendar ID resolution fix is working correctly!")
        sys.exit(0)
    else:
        logger.error("\n❌ Calendar ID resolution fix is not working correctly.")
        sys.exit(1)
