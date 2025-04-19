#!/usr/bin/env python3
"""
Test script to demonstrate and fix the calendar ID resolution issue.
"""

import sys
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("calendar_id_test")

# Add the app path
sys.path.append(".")

# Import the relevant modules
from app.cli.calendar_service import get_calendar_service, get_selected_calendars
from app.cli.event_retrieval import get_events_in_range


def demonstrate_issue():
    """Demonstrate the issue with literal calendar IDs like 'work'."""
    logger.info("=== Demonstrating Calendar ID Resolution Issue ===")

    # Set up a date range for testing
    now = datetime.now()
    start_time = now
    end_time = now + timedelta(days=7)

    # 1. First try with the problematic literal ID "work"
    logger.info("Testing with literal 'work' as calendar ID...")
    try:
        work_events = get_events_in_range(start_time, end_time, calendar_id="work")
        logger.info(f"Found {len(work_events)} events in 'work' calendar")
    except Exception as e:
        logger.error(f"Error when using 'work' directly as calendar ID: {e}")

    # 2. Get the service to check available calendars
    service = get_calendar_service()
    if not service:
        logger.error("Failed to get calendar service")
        return

    # List all available calendars for reference
    calendars = get_selected_calendars(service)
    logger.info(f"Available calendars ({len(calendars)}):")
    for cal in calendars:
        cal_id = cal.get("id")
        cal_name = cal.get("summaryOverride", cal.get("summary", "Unknown"))
        logger.info(f"  - {cal_name} (ID: {cal_id})")

    # 3. Manually find a calendar with "work" in the name
    work_calendars = [
        cal
        for cal in calendars
        if "work" in cal.get("summary", "").lower()
        or "work" in cal.get("summaryOverride", "").lower()
    ]

    if work_calendars:
        work_cal = work_calendars[0]
        work_cal_id = work_cal.get("id")
        work_cal_name = work_cal.get(
            "summaryOverride", work_cal.get("summary", "Unknown")
        )

        logger.info(
            f"Found matching work calendar: {work_cal_name} (ID: {work_cal_id})"
        )

        # Try fetching with the correct ID
        try:
            correct_events = get_events_in_range(
                start_time, end_time, calendar_id=work_cal_id
            )
            logger.info(
                f"Successfully found {len(correct_events)} events using correct ID"
            )
        except Exception as e:
            logger.error(f"Error even with correct ID: {e}")
    else:
        logger.info("No calendar with 'work' in the name was found")


if __name__ == "__main__":
    demonstrate_issue()
