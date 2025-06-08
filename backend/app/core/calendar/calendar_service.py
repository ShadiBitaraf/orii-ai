"""
Calendar service for the CLI.
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union
import json

# Try to import Google API libraries, but provide fallbacks if not available
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    GOOGLE_APIS_AVAILABLE = True
except ImportError:
    GOOGLE_APIS_AVAILABLE = False

# Import from utils to avoid circular dependencies
from ...utils.cache_utils import get_cached_data, set_cached_data
from ...utils.monitoring_utils import record_calendar_request
from ...utils.icalendar_utils import (
    google_event_to_dict,
    dict_to_google_event,
    generate_ics_file,
    parse_ics_file,
    event_to_dict,
)

logger = logging.getLogger(__name__)

# Cache for calendar data to avoid repeated API calls
CALENDAR_CACHE = {}

# Scopes for calendar operations
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service() -> Any:
    """Get or refresh Google Calendar API credentials and return service.

    Returns:
        Google Calendar service object or None if not available
    """
    # Only use real service, no mock fallback
    if GOOGLE_APIS_AVAILABLE:
        try:
            # First check if we need to create credentials.json from environment variables
            if (
                not os.path.exists("credentials.json")
                and os.environ.get("GOOGLE_CLIENT_ID")
                and os.environ.get("GOOGLE_CLIENT_SECRET")
            ):
                logger.info("Creating credentials.json from environment variables")
                client_config = {
                    "installed": {
                        "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
                        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": [
                            "urn:ietf:wg:oauth:2.0:oob",
                            "http://localhost",
                        ],
                    }
                }

                # Write the credentials.json file
                with open("credentials.json", "w") as f:
                    json.dump(client_config, f)
                logger.info("Successfully created credentials.json file")

            creds = None
            # The file token.json stores the user's access and refresh tokens, and is
            # created automatically when the authorization flow completes for the first time.
            if os.path.exists("token.json"):
                creds = Credentials.from_authorized_user_file("token.json", SCOPES)

            # If there are no (valid) credentials available, let the user log in.
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif os.path.exists("credentials.json"):
                    flow = InstalledAppFlow.from_client_secrets_file(
                        "credentials.json", SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                else:
                    logger.warning(
                        "No credentials.json found. Cannot authenticate with Google Calendar."
                    )
                    raise FileNotFoundError("credentials.json not found")

                # Save the credentials for the next run
                with open("token.json", "w") as token:
                    token.write(creds.to_json())

            # Return the calendar service
            service = build("calendar", "v3", credentials=creds)
            logger.info(
                "Successfully created real Google Calendar service with iCalendar protocol support"
            )
            return service

        except Exception as e:
            logger.error(f"Error creating real calendar service: {str(e)}")
            # No fallback to mock service
            raise Exception(f"Cannot initialize calendar service: {str(e)}")

    # If Google APIs aren't available, raise exception - no mock fallback
    logger.error("Google APIs not available and mock services disabled")
    raise ImportError(
        "Google Calendar API libraries not available and mock services are disabled"
    )


def get_calendar_timezone(service, calendar_id="primary"):
    """
    Get timezone setting for a calendar.

    Args:
        service: Google Calendar service
        calendar_id: Calendar ID (default: primary)

    Returns:
        Timezone string (e.g., 'America/Los_Angeles')
    """
    # Check cache first to avoid API call
    cache_key = f"calendar_timezone_{calendar_id}"
    cached_timezone = get_cached_data(cache_key)
    if cached_timezone:
        return cached_timezone

    start_time_perf = time.time()
    try:
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        timezone = calendar.get("timeZone", "UTC")

        # Cache the timezone
        set_cached_data(cache_key, timezone, expiration=86400)  # Cache for 24 hours

        # Record performance
        duration = time.time() - start_time_perf
        record_calendar_request("get_timezone", True, None, duration)
        return timezone
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("get_timezone", False, str(e), duration)
        logger.error(f"Error getting calendar timezone: {e}")
        return "UTC"  # Default to UTC if there's an error


def get_calendar_list(service):
    """
    Get list of calendars for the user.

    Args:
        service: Google Calendar service

    Returns:
        List of calendar dictionaries
    """
    start_time_perf = time.time()
    try:
        # Always get fresh data from the API to avoid issues
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get("items", [])

        # Record performance
        duration = time.time() - start_time_perf
        record_calendar_request("get_calendars", True, None, duration)

        logger.info(f"Retrieved {len(calendars)} calendars from Google Calendar API")
        return calendars
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("get_calendars", False, str(e), duration)
        logger.error(f"Error getting calendar list: {e}")
        return []


def get_selected_calendars(service, calendar_ids=None):
    """
    Get selected calendars or all calendars if none specified.
    Only returns calendars that are visible (not hidden) in the user's Google Calendar.

    Args:
        service: Google Calendar service
        calendar_ids: List of calendar IDs to include

    Returns:
        List of calendar dictionaries
    """
    # Get fresh calendar list directly from the API
    all_calendars = get_calendar_list(service)

    # Filter out hidden calendars - in Google Calendar API,
    # calendars have a "selected" property which indicates if they're visible
    # According to API docs: "selected" default is False, so we need explicit True
    visible_calendars = [
        cal
        for cal in all_calendars
        if cal.get("selected") is True and not cal.get("hidden", False)
    ]

    logger.info(
        f"Found {len(visible_calendars)} visible calendars out of {len(all_calendars)} total calendars"
    )

    for cal in visible_calendars:
        display_name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
        logger.info(f"Visible calendar: {display_name} (ID: {cal.get('id')})")

    # If specific calendar IDs are requested, filter the visible calendars further
    if calendar_ids:
        filtered_calendars = [
            cal for cal in visible_calendars if cal.get("id") in calendar_ids
        ]
        logger.info(
            f"Filtered to {len(filtered_calendars)} calendars based on requested IDs"
        )
        return filtered_calendars

    return visible_calendars


def get_events(
    service,
    calendar_id="primary",
    time_min=None,
    time_max=None,
    max_results=10,
    search_query=None,
    single_events=True,
    orderby="startTime",
):
    """
    Get events from a calendar.

    Args:
        service: Google Calendar service
        calendar_id: Calendar ID (default: primary)
        time_min: Start time (RFC3339 timestamp)
        time_max: End time (RFC3339 timestamp)
        max_results: Maximum number of results to return
        search_query: Optional search term to filter events
        single_events: Whether to expand recurring events
        orderby: How to order the results

    Returns:
        List of event dictionaries with standardized format
    """
    # Default time range if not specified (today and next 7 days)
    if not time_min:
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()

    if not time_max:
        now = datetime.now(timezone.utc)
        time_max = (now + timedelta(days=7)).isoformat()

    # Create cache key based on parameters
    cache_params = f"{calendar_id}_{time_min}_{time_max}_{max_results}_{search_query}_{single_events}_{orderby}"
    cache_key = f"events_{hash(cache_params)}"

    # Check cache first
    cached_events = get_cached_data(cache_key)
    if cached_events:
        return cached_events

    start_time_perf = time.time()
    try:
        # Prepare parameters
        params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": single_events,
            "orderBy": orderby,
        }

        # Add search query if provided
        if search_query:
            params["q"] = search_query

        # Execute API call
        events_result = service.events().list(**params).execute()
        google_events = events_result.get("items", [])

        # Convert to standardized dictionary format
        standardized_events = [google_event_to_dict(event) for event in google_events]

        # Add calendar information to each event
        try:
            calendar = service.calendars().get(calendarId=calendar_id).execute()
            calendar_name = calendar.get("summary", calendar_id)

            for event in standardized_events:
                event["calendar_id"] = calendar_id
                event["calendar_name"] = calendar_name
        except:
            # If we can't get calendar details, use the ID
            for event in standardized_events:
                event["calendar_id"] = calendar_id
                event["calendar_name"] = calendar_id

        # Cache the results (short expiration since events can change)
        set_cached_data(
            cache_key, standardized_events, expiration=300
        )  # Cache for 5 minutes

        # Record performance
        duration = time.time() - start_time_perf
        record_calendar_request("get_events", True, None, duration)

        return standardized_events
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("get_events", False, str(e), duration)
        logger.error(f"Error getting events: {e}")
        return []


def get_event(service, event_id, calendar_id="primary"):
    """
    Get a specific event by ID.

    Args:
        service: Google Calendar service
        event_id: Event ID
        calendar_id: Calendar ID (default: primary)

    Returns:
        Event dictionary with standardized format or None if not found
    """
    # Create cache key
    cache_key = f"event_{calendar_id}_{event_id}"

    # Check cache first
    cached_event = get_cached_data(cache_key)
    if cached_event:
        return cached_event

    start_time_perf = time.time()
    try:
        # Execute API call
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Convert to standardized dictionary format
        standardized_event = google_event_to_dict(event)

        # Add calendar information
        try:
            calendar = service.calendars().get(calendarId=calendar_id).execute()
            calendar_name = calendar.get("summary", calendar_id)
            standardized_event["calendar_id"] = calendar_id
            standardized_event["calendar_name"] = calendar_name
        except:
            standardized_event["calendar_id"] = calendar_id
            standardized_event["calendar_name"] = calendar_id

        # Cache the result (short expiration since event can change)
        set_cached_data(
            cache_key, standardized_event, expiration=300
        )  # Cache for 5 minutes

        # Record performance
        duration = time.time() - start_time_perf
        record_calendar_request("get_event", True, None, duration)

        return standardized_event
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("get_event", False, str(e), duration)
        logger.error(f"Error getting event: {e}")
        return None


def export_events_to_ics(
    service, calendar_id="primary", time_min=None, time_max=None, filename=None
):
    """
    Export events from a calendar to an iCalendar (.ics) file.

    Args:
        service: Google Calendar service
        calendar_id: Calendar ID (default: primary)
        time_min: Start time (RFC3339 timestamp)
        time_max: End time (RFC3339 timestamp)
        filename: Output filename (default: calendar_export.ics)

    Returns:
        Path to the generated .ics file or None on failure
    """
    start_time_perf = time.time()
    try:
        # Set default filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"calendar_export_{timestamp}.ics"

        # Get events
        events = get_events(
            service,
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=1000,  # Increase to get more events
            single_events=True,
        )

        # Get calendar details for the export
        try:
            calendar = service.calendars().get(calendarId=calendar_id).execute()
            calendar_name = calendar.get("summary", calendar_id)
            calendar_timezone = calendar.get("timeZone", "UTC")
        except:
            calendar_name = calendar_id
            calendar_timezone = "UTC"

        # Generate iCalendar file
        ics_path = generate_ics_file(
            events,
            filename=filename,
            calendar_name=calendar_name,
            timezone=calendar_timezone,
        )

        # Record performance
        duration = time.time() - start_time_perf
        record_calendar_request("export_ics", True, None, duration)

        return ics_path
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("export_ics", False, str(e), duration)
        logger.error(f"Error exporting events to ICS: {e}")
        return None


def import_events_from_ics(service, ics_file, calendar_id="primary"):
    """
    Import events from an iCalendar (.ics) file to a calendar.

    Args:
        service: Google Calendar service
        ics_file: Path to .ics file
        calendar_id: Calendar ID to import events into (default: primary)

    Returns:
        Dictionary with import results (success count, error count, errors)
    """
    start_time_perf = time.time()
    try:
        # Parse the .ics file
        parsed_events = parse_ics_file(ics_file)

        results = {
            "total": len(parsed_events),
            "success": 0,
            "errors": 0,
            "error_details": [],
        }

        # Import each event
        for event_dict in parsed_events:
            try:
                # Convert to Google Calendar format
                google_event = dict_to_google_event(event_dict)

                # Check if event already exists (by UID if available)
                uid = event_dict.get("uid")
                if uid:
                    # Try to find existing event with this UID
                    existing_events = []
                    try:
                        # Search by extended property
                        query = {
                            "q": f"uid:{uid}",
                            "calendarId": calendar_id,
                            "privateExtendedProperty": [f"uid={uid}"],
                        }
                        existing_events = (
                            service.events().list(**query).execute().get("items", [])
                        )
                    except:
                        pass

                    if existing_events:
                        # Update existing event
                        existing_event = existing_events[0]
                        service.events().update(
                            calendarId=calendar_id,
                            eventId=existing_event["id"],
                            body=google_event,
                        ).execute()
                    else:
                        # Create new event
                        service.events().insert(
                            calendarId=calendar_id, body=google_event
                        ).execute()
                else:
                    # No UID, create new event
                    service.events().insert(
                        calendarId=calendar_id, body=google_event
                    ).execute()

                results["success"] += 1
            except Exception as e:
                results["errors"] += 1
                results["error_details"].append(
                    {
                        "event": event_dict.get("summary", "Unknown event"),
                        "error": str(e),
                    }
                )

        # Record performance
        duration = time.time() - start_time_perf
        record_calendar_request("import_ics", True, None, duration)

        return results
    except Exception as e:
        # Record error
        duration = time.time() - start_time_perf
        record_calendar_request("import_ics", False, str(e), duration)
        logger.error(f"Error importing events from ICS: {e}")
        return {
            "total": 0,
            "success": 0,
            "errors": 1,
            "error_details": [{"event": "File processing", "error": str(e)}],
        }


def get_visible_calendars():
    """Helper function to get visible and selected calendars.

    Returns:
        List of formatted calendar information dictionaries.
    """
    try:
        service = get_calendar_service()
        if not service:
            logger.error("Failed to get calendar service")
            return []

        selected_calendars = get_selected_calendars(service)
        if not selected_calendars:
            logger.debug("No selected calendars found")
            return []

        # Format for display
        formatted_calendars = []
        for cal in selected_calendars:
            # Use summaryOverride if available, otherwise fall back to summary
            display_name = cal.get("summaryOverride", cal.get("summary", "Unnamed"))
            primary_marker = " (primary)" if cal.get("primary", False) else ""

            formatted_calendars.append(
                {
                    "summary": display_name + primary_marker,
                    "id": cal.get("id", ""),
                    "color": cal.get("backgroundColor", "#000000"),
                    "primary": cal.get("primary", False),
                }
            )

        logger.debug(f"Found {len(formatted_calendars)} visible calendars")
        return formatted_calendars
    except Exception as e:
        logger.error(f"Error getting visible calendars: {e}")
        return []
