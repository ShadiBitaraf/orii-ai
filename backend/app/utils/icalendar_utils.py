"""
iCalendar protocol utilities for standardized calendar operations.

This module provides functions for working with the iCalendar (RFC 5545) format,
facilitating interoperability with various calendar systems.
"""

import uuid
import logging
import pytz
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Union
from icalendar import Calendar, Event, vDatetime, vDate, vText, vCalAddress

logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEZONE = "UTC"
DEFAULT_PRODID = "-//Orii AI//Calendar Assistant//EN"


def create_calendar(
    name: str = "Orii Calendar",
    timezone: str = DEFAULT_TIMEZONE,
    description: str = None,
) -> Calendar:
    """
    Create a new iCalendar Calendar object.

    Args:
        name: Calendar name
        timezone: Calendar timezone
        description: Calendar description

    Returns:
        iCalendar Calendar object
    """
    cal = Calendar()
    cal.add("prodid", DEFAULT_PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    cal.add("x-wr-calname", name)
    cal.add("x-wr-timezone", timezone)

    if description:
        cal.add("x-wr-caldesc", description)

    return cal


def create_event_from_details(event_details: Dict[str, Any]) -> Event:
    """
    Create an iCalendar Event from details dictionary.

    Args:
        event_details: Dictionary with event details

    Returns:
        iCalendar Event object
    """
    event = Event()

    # Generate a UUID if not provided
    event_uid = event_details.get("uid", str(uuid.uuid4()))
    event.add("uid", event_uid)

    # Add summary (title)
    summary = event_details.get("summary", "Untitled Event")
    event.add("summary", summary)

    # Add description
    if "description" in event_details and event_details["description"]:
        event.add("description", event_details["description"])

    # Add location
    if "location" in event_details and event_details["location"]:
        event.add("location", event_details["location"])

    # Handle dates and times
    is_all_day = event_details.get("is_all_day", False)
    timezone_str = event_details.get("timezone", DEFAULT_TIMEZONE)
    try:
        tz = pytz.timezone(timezone_str)
    except:
        tz = pytz.UTC

    if is_all_day:
        # All-day event
        start_date = event_details.get("start_date")

        # Convert datetime to date if needed
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        elif isinstance(start_date, str):
            try:
                start_date = datetime.fromisoformat(start_date).date()
            except:
                # Just use today if parsing fails
                start_date = date.today()

        event.add("dtstart", vDate(start_date))

        # End date is optional
        end_date = event_details.get("end_date")
        if end_date:
            # Convert datetime to date if needed
            if isinstance(end_date, datetime):
                end_date = end_date.date()
            elif isinstance(end_date, str):
                try:
                    end_date = datetime.fromisoformat(end_date).date()
                except:
                    # Use start_date + 1 day if parsing fails
                    end_date = start_date + timedelta(days=1)

            # In iCalendar, the end date is exclusive, so add 1 day
            event.add("dtend", vDate(end_date + timedelta(days=1)))
        else:
            # Default to 1 day event
            event.add("dtend", vDate(start_date + timedelta(days=1)))
    else:
        # Timed event
        start_time = event_details.get("start_time")

        # Ensure we have a datetime with timezone
        if not start_time:
            # Default to now if not provided
            start_time = datetime.now(tz)
        elif isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time)
                if start_time.tzinfo is None:
                    start_time = tz.localize(start_time)
            except:
                start_time = datetime.now(tz)
        elif start_time.tzinfo is None:
            start_time = tz.localize(start_time)

        event.add("dtstart", vDatetime(start_time))

        # End time is optional
        end_time = event_details.get("end_time")
        if end_time:
            # Ensure we have a datetime with timezone
            if isinstance(end_time, str):
                try:
                    end_time = datetime.fromisoformat(end_time)
                except:
                    # Default to start_time + 1 hour
                    end_time = start_time + timedelta(hours=1)
            elif end_time.tzinfo is None:
                end_time = tz.localize(end_time)
        else:
            # Default to 1 hour event
            end_time = start_time + timedelta(hours=1)

        event.add("dtend", vDatetime(end_time))

    # Add creation timestamp
    event.add("dtstamp", vDatetime(datetime.now(pytz.UTC)))

    # Handle recurrence
    if "recurrence" in event_details and event_details["recurrence"]:
        event.add("rrule", event_details["recurrence"])

    # Handle attendees
    if "attendees" in event_details and event_details["attendees"]:
        for attendee in event_details["attendees"]:
            if isinstance(attendee, dict):
                email = attendee.get("email")
                name = attendee.get("name", "")
                status = attendee.get("status", "NEEDS-ACTION")
                role = attendee.get("role", "REQ-PARTICIPANT")

                attendee_str = f"mailto:{email}"
                cal_attendee = vCalAddress(attendee_str)
                cal_attendee.params["cn"] = vText(name or email)
                cal_attendee.params["ROLE"] = vText(role)
                cal_attendee.params["PARTSTAT"] = vText(status)
                cal_attendee.params["RSVP"] = vText("TRUE")

                event.add("attendee", cal_attendee)
            elif isinstance(attendee, str):
                # Simple email string
                attendee_str = f"mailto:{attendee}"
                cal_attendee = vCalAddress(attendee_str)
                cal_attendee.params["cn"] = vText(attendee)
                cal_attendee.params["ROLE"] = vText("REQ-PARTICIPANT")
                cal_attendee.params["PARTSTAT"] = vText("NEEDS-ACTION")
                cal_attendee.params["RSVP"] = vText("TRUE")

                event.add("attendee", cal_attendee)

    # Handle organizer
    if "organizer" in event_details:
        organizer = event_details["organizer"]
        if isinstance(organizer, dict):
            email = organizer.get("email")
            name = organizer.get("name", "")

            organizer_str = f"mailto:{email}"
            cal_organizer = vCalAddress(organizer_str)
            cal_organizer.params["cn"] = vText(name or email)

            event.add("organizer", cal_organizer)
        elif isinstance(organizer, str):
            # Simple email string
            organizer_str = f"mailto:{organizer}"
            cal_organizer = vCalAddress(organizer_str)
            cal_organizer.params["cn"] = vText(organizer)

            event.add("organizer", cal_organizer)

    # Handle categories
    if "categories" in event_details and event_details["categories"]:
        categories = event_details["categories"]
        if isinstance(categories, list):
            event.add("categories", categories)
        elif isinstance(categories, str):
            event.add("categories", [categories])

    # Handle status
    if "status" in event_details and event_details["status"]:
        event.add("status", event_details["status"].upper())

    # Handle transparency
    if "transparency" in event_details:
        transparency = "TRANSPARENT" if event_details["transparency"] else "OPAQUE"
        event.add("transp", transparency)

    # Handle custom properties
    if "custom_properties" in event_details and event_details["custom_properties"]:
        for key, value in event_details["custom_properties"].items():
            event.add(key, value)

    return event


def event_to_dict(event: Event) -> Dict[str, Any]:
    """
    Convert an iCalendar Event to a dictionary.

    Args:
        event: iCalendar Event object

    Returns:
        Dictionary with event details
    """
    result = {}

    # Extract UID
    if "uid" in event:
        result["uid"] = str(event["uid"])

    # Extract summary (title)
    if "summary" in event:
        result["summary"] = str(event["summary"])
    else:
        result["summary"] = "Untitled Event"

    # Extract description
    if "description" in event:
        result["description"] = str(event["description"])

    # Extract location
    if "location" in event:
        result["location"] = str(event["location"])

    # Extract dates and times
    if "dtstart" in event:
        dtstart = event["dtstart"]
        dtstart_param = event["dtstart"].params

        if isinstance(dtstart.dt, date) and not isinstance(dtstart.dt, datetime):
            # All-day event
            result["is_all_day"] = True
            result["start_date"] = dtstart.dt.isoformat()
        else:
            # Timed event
            result["is_all_day"] = False
            result["start_time"] = dtstart.dt.isoformat()

        # Extract timezone if present
        if "tzid" in dtstart_param:
            result["timezone"] = str(dtstart_param["tzid"])

    if "dtend" in event:
        dtend = event["dtend"]

        if isinstance(dtend.dt, date) and not isinstance(dtend.dt, datetime):
            # All-day event
            # In iCalendar, the end date is exclusive, so subtract 1 day
            end_date = dtend.dt - timedelta(days=1)
            result["end_date"] = end_date.isoformat()
        else:
            # Timed event
            result["end_time"] = dtend.dt.isoformat()

    # Extract recurrence
    if "rrule" in event:
        result["recurrence"] = event["rrule"]

    # Extract attendees
    if "attendee" in event:
        attendees = []
        for attendee in event.get("attendee", []):
            if not attendee:
                continue

            attendee_email = str(attendee).replace("mailto:", "")
            attendee_dict = {"email": attendee_email}

            # Extract attendee parameters
            params = getattr(attendee, "params", {})
            if "cn" in params:
                attendee_dict["name"] = str(params["cn"])
            if "PARTSTAT" in params:
                attendee_dict["status"] = str(params["PARTSTAT"])
            if "ROLE" in params:
                attendee_dict["role"] = str(params["ROLE"])

            attendees.append(attendee_dict)

        result["attendees"] = attendees

    # Extract organizer
    if "organizer" in event:
        organizer = event["organizer"]
        if organizer:
            organizer_email = str(organizer).replace("mailto:", "")
            organizer_dict = {"email": organizer_email}

            # Extract organizer parameters
            params = getattr(organizer, "params", {})
            if "cn" in params:
                organizer_dict["name"] = str(params["cn"])

            result["organizer"] = organizer_dict

    # Extract categories
    if "categories" in event:
        categories = event["categories"]
        if isinstance(categories, list):
            result["categories"] = [str(cat) for cat in categories]
        else:
            result["categories"] = [str(categories)]

    # Extract status
    if "status" in event:
        result["status"] = str(event["status"])

    # Extract transparency
    if "transp" in event:
        result["transparency"] = str(event["transp"]) == "TRANSPARENT"

    return result


def dict_to_google_event(event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a dictionary to a Google Calendar event format with comprehensive field support.

    Args:
        event_dict: Dictionary with event details

    Returns:
        Google Calendar event dictionary
    """
    google_event = {
        "summary": event_dict.get("summary", "Untitled Event"),
    }

    # Add description
    if "description" in event_dict and event_dict["description"]:
        google_event["description"] = event_dict["description"]

    # Add location
    if "location" in event_dict and event_dict["location"]:
        google_event["location"] = event_dict["location"]

    # Handle UID as extended property
    if "uid" in event_dict and event_dict["uid"]:
        uid = event_dict["uid"]
        google_event["extendedProperties"] = {"private": {"uid": uid}}
        # Also add as an X-property for better compatibility
        google_event["extendedProperties"]["private"][
            "X-GOOGLE-CALENDAR-CONTENT-UID"
        ] = uid

    # Handle dates and times
    is_all_day = event_dict.get("is_all_day", False) or event_dict.get("all_day", False)
    timezone_str = event_dict.get("timezone", DEFAULT_TIMEZONE)

    if is_all_day:
        # All-day event
        start_date = event_dict.get("start_date") or event_dict.get("start_datetime")
        if not start_date:
            start_date = date.today().isoformat()
        elif "T" in str(start_date):
            # Convert datetime to date
            start_date = (
                datetime.fromisoformat(str(start_date).split("T")[0]).date().isoformat()
            )

        google_event["start"] = {"date": start_date}

        # End date is optional
        end_date = event_dict.get("end_date") or event_dict.get("end_datetime")
        if not end_date:
            # Default to 1 day event
            end_date = (
                datetime.fromisoformat(start_date).date() + timedelta(days=1)
            ).isoformat()
        elif "T" in str(end_date):
            # Convert datetime to date
            end_date = (
                datetime.fromisoformat(str(end_date).split("T")[0]).date().isoformat()
            )

        google_event["end"] = {"date": end_date}
    else:
        # Timed event - support both start_time and start_datetime fields
        start_time = event_dict.get("start_time") or event_dict.get("start_datetime")
        if not start_time:
            # Default to now
            start_time = (
                datetime.now().astimezone(pytz.timezone(timezone_str)).isoformat()
            )

        # Ensure timezone info is properly formatted
        if (
            not start_time.endswith("Z")
            and "+" not in start_time
            and "-" not in start_time[-6:]
        ):
            # Add timezone info if missing
            start_time = start_time + ("+00:00" if timezone_str == "UTC" else "")

        google_event["start"] = {"dateTime": start_time, "timeZone": timezone_str}

        # End time is optional - support both end_time and end_datetime fields
        end_time = event_dict.get("end_time") or event_dict.get("end_datetime")
        if not end_time:
            # Default to 1 hour event
            try:
                # Parse start_time properly to add 1 hour
                if start_time.endswith("Z"):
                    start_dt = datetime.fromisoformat(start_time[:-1] + "+00:00")
                elif "+" in start_time or start_time.count("-") >= 3:
                    start_dt = datetime.fromisoformat(start_time)
                else:
                    start_dt = datetime.fromisoformat(start_time)

                end_dt = start_dt + timedelta(hours=1)
                end_time = end_dt.isoformat()
            except Exception:
                # Fallback if parsing fails
                end_time = (
                    datetime.fromisoformat(start_time.split("+")[0].split("Z")[0])
                    + timedelta(hours=1)
                ).isoformat()

        # Ensure end time timezone format matches start time
        if (
            not end_time.endswith("Z")
            and "+" not in end_time
            and "-" not in end_time[-6:]
        ):
            end_time = end_time + ("+00:00" if timezone_str == "UTC" else "")

        google_event["end"] = {"dateTime": end_time, "timeZone": timezone_str}

    # Handle recurrence with enhanced RRULE support
    if "recurrence" in event_dict and event_dict["recurrence"]:
        recurrence = event_dict["recurrence"]
        if isinstance(recurrence, dict):
            # Convert from dict to RRULE string
            rrule_parts = []
            for key, value in recurrence.items():
                rrule_parts.append(f"{key}={value}")
            google_event["recurrence"] = [f"RRULE:{';'.join(rrule_parts)}"]
        elif isinstance(recurrence, str):
            # Handle both full RRULE and simple patterns
            if recurrence.startswith("RRULE:"):
                google_event["recurrence"] = [recurrence]
            elif recurrence.startswith("FREQ="):
                google_event["recurrence"] = [f"RRULE:{recurrence}"]
            else:
                # Simple patterns
                simple_patterns = {
                    "daily": "FREQ=DAILY",
                    "weekly": "FREQ=WEEKLY",
                    "monthly": "FREQ=MONTHLY",
                    "yearly": "FREQ=YEARLY",
                }
                rrule = simple_patterns.get(recurrence.lower(), f"FREQ=WEEKLY")
                google_event["recurrence"] = [f"RRULE:{rrule}"]
        elif isinstance(recurrence, list):
            google_event["recurrence"] = recurrence

    # Also check for recurrence_rule field
    elif "recurrence_rule" in event_dict and event_dict["recurrence_rule"]:
        recurrence_rule = event_dict["recurrence_rule"]
        if isinstance(recurrence_rule, str):
            if recurrence_rule.startswith("RRULE:"):
                google_event["recurrence"] = [recurrence_rule]
            elif recurrence_rule.startswith("FREQ="):
                google_event["recurrence"] = [f"RRULE:{recurrence_rule}"]
            else:
                # Simple patterns
                simple_patterns = {
                    "daily": "FREQ=DAILY",
                    "weekly": "FREQ=WEEKLY",
                    "monthly": "FREQ=MONTHLY",
                    "yearly": "FREQ=YEARLY",
                }
                rrule = simple_patterns.get(recurrence_rule.lower(), f"FREQ=WEEKLY")
                google_event["recurrence"] = [f"RRULE:{rrule}"]

    # Handle attendees with enhanced support
    if "attendees" in event_dict and event_dict["attendees"]:
        google_attendees = []
        for attendee in event_dict["attendees"]:
            if isinstance(attendee, dict):
                google_attendee = {}

                # Email is required
                if "email" in attendee:
                    google_attendee["email"] = attendee["email"]
                else:
                    continue  # Skip attendees without email

                # Add optional fields
                if "name" in attendee:
                    google_attendee["displayName"] = attendee["name"]
                if "status" in attendee:
                    status = attendee["status"].upper()
                    status_map = {
                        "ACCEPTED": "accepted",
                        "DECLINED": "declined",
                        "TENTATIVE": "tentative",
                        "NEEDS-ACTION": "needsAction",
                    }
                    google_attendee["responseStatus"] = status_map.get(
                        status, "needsAction"
                    )

                # Add optional organizer flag
                if attendee.get("organizer", False):
                    google_attendee["organizer"] = True

                google_attendees.append(google_attendee)

            elif isinstance(attendee, str):
                # Handle both email-only strings and "Name <email>" format
                if "<" in attendee and ">" in attendee:
                    # Parse "Name <email>" format
                    import re

                    match = re.match(r"^(.*?)\s*<([^>]+)>$", attendee.strip())
                    if match:
                        name, email = match.groups()
                        google_attendees.append(
                            {"email": email.strip(), "displayName": name.strip()}
                        )
                    else:
                        google_attendees.append({"email": attendee})
                else:
                    google_attendees.append({"email": attendee})

        if google_attendees:
            google_event["attendees"] = google_attendees

    # Handle organizer
    if "organizer" in event_dict:
        organizer = event_dict["organizer"]
        if isinstance(organizer, dict):
            google_event["organizer"] = {
                "email": organizer.get("email"),
                "displayName": organizer.get("name", ""),
            }
        elif isinstance(organizer, str):
            google_event["organizer"] = {"email": organizer}

    # Handle reminders - support both single reminder and multiple reminders
    reminders = event_dict.get("reminder_minutes") or event_dict.get("reminders")
    if reminders:
        if isinstance(reminders, (int, float)):
            # Single reminder
            google_event["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": int(reminders)}],
            }
        elif isinstance(reminders, list):
            # Multiple reminders
            overrides = []
            for reminder in reminders:
                if isinstance(reminder, (int, float)):
                    overrides.append({"method": "popup", "minutes": int(reminder)})
                elif isinstance(reminder, dict):
                    method = reminder.get("method", "popup")
                    minutes = reminder.get("minutes", 15)
                    overrides.append({"method": method, "minutes": int(minutes)})

            if overrides:
                google_event["reminders"] = {
                    "useDefault": False,
                    "overrides": overrides,
                }
    else:
        # Use default reminders
        google_event["reminders"] = {"useDefault": True}

    # Handle Google Meet integration
    if event_dict.get("add_meet", False):
        google_event["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),  # Unique request ID
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    # Handle visibility/privacy
    visibility = event_dict.get("visibility", "default")
    if visibility in ["default", "public", "private", "confidential"]:
        google_event["visibility"] = visibility

    # Handle guest permissions
    if "guests_can_modify" in event_dict:
        google_event["guestsCanModify"] = bool(event_dict["guests_can_modify"])

    if "guests_can_invite_others" in event_dict:
        google_event["guestsCanInviteOthers"] = bool(
            event_dict["guests_can_invite_others"]
        )

    if "guests_can_see_other_guests" in event_dict:
        google_event["guestsCanSeeOtherGuests"] = bool(
            event_dict["guests_can_see_other_guests"]
        )

    # Handle event color
    color_id = event_dict.get("color_id") or event_dict.get("color")
    if color_id:
        google_event["colorId"] = str(color_id)

    # Handle busy/free status (transparency)
    busy_status = event_dict.get("busy_status", "busy")
    if busy_status == "free":
        google_event["transparency"] = "transparent"
    else:
        google_event["transparency"] = "opaque"

    # Handle status
    if "status" in event_dict:
        status = event_dict["status"].upper()
        status_map = {
            "CONFIRMED": "confirmed",
            "TENTATIVE": "tentative",
            "CANCELLED": "cancelled",
        }
        google_event["status"] = status_map.get(status, "confirmed")

    # Handle event ID for updates
    if "id" in event_dict and event_dict["id"]:
        google_event["id"] = event_dict["id"]

    # Handle calendar ID (not part of event, but used for API calls)
    if "calendar_id" in event_dict:
        google_event["_calendar_id"] = event_dict["calendar_id"]

    return google_event


def google_event_to_dict(google_event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a Google Calendar event to a standardized dictionary.

    Args:
        google_event: Google Calendar event dictionary

    Returns:
        Standardized event dictionary
    """
    event_dict = {
        "id": google_event.get("id", ""),
        "summary": google_event.get("summary", "Untitled Event"),
    }

    # Extract description
    if "description" in google_event:
        event_dict["description"] = google_event["description"]

    # Extract location
    if "location" in google_event:
        event_dict["location"] = google_event["location"]

    # Extract UID from extended properties
    if "extendedProperties" in google_event:
        props = google_event["extendedProperties"]
        if "private" in props and "uid" in props["private"]:
            event_dict["uid"] = props["private"]["uid"]
        elif "private" in props and "X-GOOGLE-CALENDAR-CONTENT-UID" in props["private"]:
            event_dict["uid"] = props["private"]["X-GOOGLE-CALENDAR-CONTENT-UID"]

    # Extract dates and times
    start = google_event.get("start", {})
    end = google_event.get("end", {})

    if "date" in start:
        # All-day event
        event_dict["is_all_day"] = True
        event_dict["start_date"] = start["date"]
        event_dict["start"] = {"date": start["date"]}

        if "date" in end:
            event_dict["end_date"] = end["date"]
            event_dict["end"] = {"date": end["date"]}
    elif "dateTime" in start:
        # Timed event
        event_dict["is_all_day"] = False
        event_dict["start_time"] = start["dateTime"]
        event_dict["start"] = {"dateTime": start["dateTime"]}

        if "timeZone" in start:
            event_dict["timezone"] = start["timeZone"]

        if "dateTime" in end:
            event_dict["end_time"] = end["dateTime"]
            event_dict["end"] = {"dateTime": end["dateTime"]}

    # Get allDay flag for compatibility
    event_dict["allDay"] = event_dict.get("is_all_day", False)

    # Extract recurrence
    if "recurrence" in google_event:
        recurrence = google_event["recurrence"]
        if recurrence and isinstance(recurrence, list):
            event_dict["recurrence"] = recurrence[0] if recurrence else None

    # Extract attendees
    if "attendees" in google_event:
        attendees = []
        for attendee in google_event["attendees"]:
            attendee_dict = {"email": attendee.get("email", "")}

            if "displayName" in attendee:
                attendee_dict["name"] = attendee["displayName"]

            if "responseStatus" in attendee:
                status = attendee["responseStatus"]
                if status == "accepted":
                    attendee_dict["status"] = "ACCEPTED"
                elif status == "declined":
                    attendee_dict["status"] = "DECLINED"
                elif status == "tentative":
                    attendee_dict["status"] = "TENTATIVE"
                else:
                    attendee_dict["status"] = "NEEDS-ACTION"

            attendees.append(attendee_dict)

        event_dict["attendees"] = attendees

    # Extract organizer
    if "organizer" in google_event:
        organizer = google_event["organizer"]
        event_dict["organizer"] = {
            "email": organizer.get("email", ""),
            "name": organizer.get("displayName", ""),
        }

    # Extract status
    if "status" in google_event:
        status = google_event["status"]
        if status == "confirmed":
            event_dict["status"] = "CONFIRMED"
        elif status == "tentative":
            event_dict["status"] = "TENTATIVE"
        elif status == "cancelled":
            event_dict["status"] = "CANCELLED"

    # Extract transparency
    if "transparency" in google_event:
        event_dict["transparency"] = google_event["transparency"] == "transparent"

    # Extract color
    if "colorId" in google_event:
        event_dict["color"] = google_event["colorId"]

    return event_dict


def generate_ics_file(
    events: List[Dict[str, Any]],
    filename: str = "calendar_export.ics",
    calendar_name: str = "Exported Calendar",
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """
    Generate an iCalendar (.ics) file from a list of events.

    Args:
        events: List of event dictionaries
        filename: Output filename
        calendar_name: Calendar name for the export
        timezone: Calendar timezone

    Returns:
        Path to the generated .ics file
    """
    # Create a new calendar
    cal = create_calendar(name=calendar_name, timezone=timezone)

    # Add all events to the calendar
    for event_dict in events:
        # Convert standardized dict to iCalendar Event
        event = create_event_from_details(event_dict)
        cal.add_component(event)

    # Write the calendar to a file
    ics_data = cal.to_ical()
    with open(filename, "wb") as f:
        f.write(ics_data)

    return os.path.abspath(filename)


def parse_ics_file(ics_file: str) -> List[Dict[str, Any]]:
    """
    Parse an iCalendar (.ics) file into a list of event dictionaries.

    Args:
        ics_file: Path to the .ics file

    Returns:
        List of event dictionaries
    """
    events = []

    try:
        with open(ics_file, "rb") as f:
            cal = Calendar.from_ical(f.read())

            # Extract calendar-level properties
            calendar_name = str(cal.get("x-wr-calname", "Imported Calendar"))
            calendar_timezone = str(cal.get("x-wr-timezone", DEFAULT_TIMEZONE))

            # Process all events
            for component in cal.walk():
                if component.name == "VEVENT":
                    # Convert iCalendar Event to standardized dict
                    event_dict = event_to_dict(component)

                    # Add calendar info
                    event_dict["calendar_name"] = calendar_name
                    event_dict["calendar_timezone"] = calendar_timezone

                    events.append(event_dict)

    except Exception as e:
        logger.error(f"Error parsing ICS file: {e}")
        return []

    return events
