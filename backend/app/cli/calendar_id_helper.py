"""
Helper functions for safely resolving calendar IDs.

This module provides functions to ensure calendar IDs are valid before
using them in Google Calendar API calls, helping prevent 404 errors.
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def resolve_calendar_id(
    service, calendar_id_or_name: str, fallback_to_primary: bool = True
) -> Optional[str]:
    """
    Safely resolve a calendar ID or name to an actual valid calendar ID.

    This function helps prevent 404 errors when users specify "calendar names"
    like "work" or "personal" that aren't actual Google Calendar IDs.

    Args:
        service: Google Calendar API service
        calendar_id_or_name: Either a calendar ID or a search term like "work"
        fallback_to_primary: Whether to fall back to the primary calendar if no match is found

    Returns:
        A valid calendar ID or None if no calendar could be found
    """
    from ..core.calendar.calendar_service import get_selected_calendars

    try:
        # Get all available calendars
        all_calendars = get_selected_calendars(service)

        if not all_calendars:
            logger.warning("No calendars available")
            return None

        # First, check for exact ID match
        exact_match = [
            cal for cal in all_calendars if cal.get("id") == calendar_id_or_name
        ]
        if exact_match:
            return exact_match[0].get("id")

        # Second, search for name match
        name_matches = [
            cal
            for cal in all_calendars
            if (
                calendar_id_or_name.lower() in cal.get("summary", "").lower()
                or (
                    cal.get("summaryOverride")
                    and calendar_id_or_name.lower()
                    in cal.get("summaryOverride", "").lower()
                )
            )
        ]

        if name_matches:
            match = name_matches[0]
            match_id = match.get("id")
            match_name = match.get("summaryOverride", match.get("summary", "Unknown"))
            logger.info(
                f"Resolved '{calendar_id_or_name}' to calendar '{match_name}' ({match_id})"
            )
            return match_id

        # No match found, fall back to primary if requested
        if fallback_to_primary:
            primary = [cal for cal in all_calendars if cal.get("primary", False)]
            if primary:
                primary_id = primary[0].get("id")
                primary_name = primary[0].get(
                    "summaryOverride", primary[0].get("summary", "Unknown")
                )
                logger.warning(
                    f"No calendar found matching '{calendar_id_or_name}', "
                    f"falling back to primary: {primary_name} ({primary_id})"
                )
                return primary_id

            # If no primary, just return the first available calendar
            if all_calendars:
                first_cal = all_calendars[0]
                first_id = first_cal.get("id")
                first_name = first_cal.get(
                    "summaryOverride", first_cal.get("summary", "Unknown")
                )
                logger.warning(
                    f"No calendar found matching '{calendar_id_or_name}' and no primary. "
                    f"Using first available: {first_name} ({first_id})"
                )
                return first_id

        logger.error(f"Could not find calendar matching '{calendar_id_or_name}'")
        return None

    except Exception as e:
        logger.error(f"Error resolving calendar ID: {e}")
        return None


def find_matching_calendars(service, search_term: str) -> List[Dict[str, Any]]:
    """
    Find all calendars matching a search term.

    Args:
        service: Google Calendar API service
        search_term: Search term for calendar names

    Returns:
        List of matching calendar dictionaries
    """
    from ..core.calendar.calendar_service import get_selected_calendars

    try:
        all_calendars = get_selected_calendars(service)

        if not search_term or not search_term.strip():
            return all_calendars

        # Find all matching calendars
        matching_calendars = [
            cal
            for cal in all_calendars
            if (
                search_term.lower() in cal.get("summary", "").lower()
                or (
                    cal.get("summaryOverride")
                    and search_term.lower() in cal.get("summaryOverride", "").lower()
                )
            )
        ]

        return matching_calendars

    except Exception as e:
        logger.error(f"Error finding matching calendars: {e}")
        return []
