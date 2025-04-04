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

    # Handle reminders
    if "reminders" in event_details and event_details["reminders"]:
        for reminder in event_details["reminders"]:
            valarm = event.add("valarm")
            valarm.add("action", "DISPLAY")
            valarm.add("description", f"Reminder: {summary}")

            # Set trigger time
            minutes = reminder.get("minutes", 15)
            valarm.add("trigger", timedelta(minutes=-minutes))

    # Handle transparency (blocking or free)
    if event_details.get("transparency") == "transparent":
        event.add("transp", "TRANSPARENT")  # Free
    else:
        event.add("transp", "OPAQUE")  # Busy/blocking

    # Add status (CONFIRMED, TENTATIVE, CANCELLED)
    status = event_details.get("status", "CONFIRMED")
    event.add("status", status.upper())

    # Add extra properties for compatibility with Google Calendar
    if "color_id" in event_details:
        event["X-GOOGLE-COLORID"] = event_details["color_id"]

    # Add meeting link if available
    if "meeting_link" in event_details:
        event["X-MEETING-URL"] = event_details["meeting_link"]

    # Add extended properties
    if "extended_properties" in event_details:
        for key, value in event_details["extended_properties"].items():
            event[f"X-PROP-{key}"] = str(value)

    return event


def event_to_dict(event: Event) -> Dict[str, Any]:
    """
    Convert an iCalendar Event to a standardized dictionary.

    Args:
        event: iCalendar Event object

    Returns:
        Dictionary with event details
    """
    result = {}

    # Get basic properties
    result["uid"] = str(event.get("uid", ""))
    result["summary"] = str(event.get("summary", "Untitled Event"))

    if "description" in event:
        result["description"] = str(event["description"])

    if "location" in event:
        result["location"] = str(event["location"])

    # Handle date/time
    if "dtstart" in event:
        dt_start = event["dtstart"].dt
        if isinstance(dt_start, date) and not isinstance(dt_start, datetime):
            # All-day event
            result["is_all_day"] = True
            result["start_date"] = dt_start

            if "dtend" in event:
                dt_end = event["dtend"].dt
                if isinstance(dt_end, date):
                    # In iCalendar, end date is exclusive, so subtract 1 day
                    result["end_date"] = dt_end - timedelta(days=1)
        else:
            # Timed event
            result["is_all_day"] = False
            result["start_time"] = dt_start

            if "dtend" in event:
                result["end_time"] = event["dtend"].dt

    # Handle recurrence
    if "rrule" in event:
        result["recurrence"] = str(event["rrule"])

    # Handle attendees
    if "attendee" in event:
        attendees = []
        for attendee in event.get("attendee", []):
            email = str(attendee).replace("mailto:", "")
            attendee_dict = {"email": email}

            if "cn" in attendee.params:
                attendee_dict["name"] = str(attendee.params["cn"])

            if "PARTSTAT" in attendee.params:
                attendee_dict["status"] = str(attendee.params["PARTSTAT"])

            if "ROLE" in attendee.params:
                attendee_dict["role"] = str(attendee.params["ROLE"])

            attendees.append(attendee_dict)

        result["attendees"] = attendees

    # Handle organizer
    if "organizer" in event:
        organizer = event["organizer"]
        email = str(organizer).replace("mailto:", "")
        organizer_dict = {"email": email}

        if "cn" in organizer.params:
            organizer_dict["name"] = str(organizer.params["cn"])

        result["organizer"] = organizer_dict

    # Handle transparency (free/busy)
    if "transp" in event:
        transp = str(event["transp"]).upper()
        result["transparency"] = "transparent" if transp == "TRANSPARENT" else "opaque"

    # Handle status
    if "status" in event:
        result["status"] = str(event["status"])

    # Handle extended properties
    extended_props = {}
    for key, value in event.items():
        if key.startswith("X-PROP-"):
            prop_name = key[7:]  # Remove X-PROP- prefix
            extended_props[prop_name] = str(value)

    if extended_props:
        result["extended_properties"] = extended_props

    # Handle special properties
    if "X-GOOGLE-COLORID" in event:
        result["color_id"] = str(event["X-GOOGLE-COLORID"])

    if "X-MEETING-URL" in event:
        result["meeting_link"] = str(event["X-MEETING-URL"])

    return result


def dict_to_google_event(event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert our standardized dictionary to Google Calendar API format.

    Args:
        event_dict: Dictionary with event details

    Returns:
        Dictionary in Google Calendar API format
    """
    google_event = {}

    # Basic properties
    if "summary" in event_dict:
        google_event["summary"] = event_dict["summary"]

    if "description" in event_dict:
        google_event["description"] = event_dict["description"]

    if "location" in event_dict:
        google_event["location"] = event_dict["location"]

    # Handle date/time
    timezone = event_dict.get("timezone", DEFAULT_TIMEZONE)
    is_all_day = event_dict.get("is_all_day", False)

    if is_all_day:
        # All-day event
        start_date = event_dict.get("start_date")
        if start_date:
            if isinstance(start_date, datetime):
                start_date = start_date.date()

            google_event["start"] = {
                "date": (
                    start_date.isoformat()
                    if isinstance(start_date, date)
                    else start_date
                ),
                "timeZone": timezone,
            }

        end_date = event_dict.get("end_date")
        if end_date:
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            # In Google Calendar, end date is exclusive, so add 1 day
            if isinstance(end_date, date):
                end_date = end_date + timedelta(days=1)

            google_event["end"] = {
                "date": (
                    end_date.isoformat() if isinstance(end_date, date) else end_date
                ),
                "timeZone": timezone,
            }
    else:
        # Timed event
        start_time = event_dict.get("start_time")
        if start_time:
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time)
                except:
                    pass

            if isinstance(start_time, datetime):
                google_event["start"] = {
                    "dateTime": start_time.isoformat(),
                    "timeZone": timezone,
                }

        end_time = event_dict.get("end_time")
        if end_time:
            if isinstance(end_time, str):
                try:
                    end_time = datetime.fromisoformat(end_time)
                except:
                    pass

            if isinstance(end_time, datetime):
                google_event["end"] = {
                    "dateTime": end_time.isoformat(),
                    "timeZone": timezone,
                }

    # Handle recurrence
    if "recurrence" in event_dict and event_dict["recurrence"]:
        google_event["recurrence"] = [event_dict["recurrence"]]

    # Handle attendees
    if "attendees" in event_dict and event_dict["attendees"]:
        google_attendees = []
        for attendee in event_dict["attendees"]:
            if isinstance(attendee, dict):
                google_attendee = {"email": attendee["email"]}

                if "name" in attendee:
                    google_attendee["displayName"] = attendee["name"]

                if "status" in attendee:
                    google_attendee["responseStatus"] = attendee["status"]

                google_attendees.append(google_attendee)
            elif isinstance(attendee, str):
                google_attendees.append({"email": attendee})

        google_event["attendees"] = google_attendees

    # Handle organizer
    if "organizer" in event_dict:
        organizer = event_dict["organizer"]
        if isinstance(organizer, dict):
            google_organizer = {"email": organizer["email"]}

            if "name" in organizer:
                google_organizer["displayName"] = organizer["name"]

            google_event["organizer"] = google_organizer

    # Handle reminders
    if "reminders" in event_dict and event_dict["reminders"]:
        reminders = {"useDefault": False, "overrides": []}

        for reminder in event_dict["reminders"]:
            minutes = reminder.get("minutes", 15)
            reminders["overrides"].append({"method": "popup", "minutes": minutes})

        google_event["reminders"] = reminders

    # Handle color
    if "color_id" in event_dict:
        google_event["colorId"] = event_dict["color_id"]

    # Handle transparency (free/busy)
    if "transparency" in event_dict:
        google_event["transparency"] = event_dict["transparency"]

    # Handle status
    if "status" in event_dict:
        google_event["status"] = event_dict["status"]

    # Handle meeting link through conferenceData
    if "meeting_link" in event_dict:
        google_event["conferenceData"] = {
            "entryPoints": [
                {
                    "entryPointType": "video",
                    "uri": event_dict["meeting_link"],
                    "label": "Video Link",
                }
            ]
        }

    # Handle extended properties
    if "extended_properties" in event_dict:
        google_event["extendedProperties"] = {
            "private": event_dict["extended_properties"]
        }

    # Add UID as extended property for compatibility
    if "uid" in event_dict:
        if "extendedProperties" not in google_event:
            google_event["extendedProperties"] = {"private": {}}

        google_event["extendedProperties"]["private"]["uid"] = event_dict["uid"]

    return google_event


def google_event_to_dict(google_event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Google Calendar API event to our standardized dictionary.

    Args:
        google_event: Google Calendar API event

    Returns:
        Dictionary with standardized event details
    """
    result = {}

    # Basic properties
    result["uid"] = google_event.get("id", "")
    result["summary"] = google_event.get("summary", "Untitled Event")

    if "description" in google_event:
        result["description"] = google_event["description"]

    if "location" in google_event:
        result["location"] = google_event["location"]

    # Handle date/time
    start = google_event.get("start", {})
    end = google_event.get("end", {})

    # Determine timezone
    timezone = start.get("timeZone") or end.get("timeZone") or DEFAULT_TIMEZONE
    result["timezone"] = timezone

    if "date" in start:
        # All-day event
        result["is_all_day"] = True

        try:
            start_date = datetime.fromisoformat(start["date"]).date()
            result["start_date"] = start_date

            if "date" in end:
                end_date = datetime.fromisoformat(end["date"]).date()
                # Google Calendar end date is exclusive, so subtract 1 day
                result["end_date"] = end_date - timedelta(days=1)
        except:
            # Fallback if date parsing fails
            result["start_date"] = start["date"]
            if "date" in end:
                result["end_date"] = end["date"]
    elif "dateTime" in start:
        # Timed event
        result["is_all_day"] = False

        try:
            start_time = datetime.fromisoformat(
                start["dateTime"].replace("Z", "+00:00")
            )
            result["start_time"] = start_time

            if "dateTime" in end:
                end_time = datetime.fromisoformat(
                    end["dateTime"].replace("Z", "+00:00")
                )
                result["end_time"] = end_time
        except:
            # Fallback if datetime parsing fails
            result["start_time"] = start["dateTime"]
            if "dateTime" in end:
                result["end_time"] = end["dateTime"]

    # Handle recurrence
    if "recurrence" in google_event and google_event["recurrence"]:
        result["recurrence"] = google_event["recurrence"][0]

    # Handle attendees
    if "attendees" in google_event:
        attendees = []
        for attendee in google_event["attendees"]:
            attendee_dict = {"email": attendee["email"]}

            if "displayName" in attendee:
                attendee_dict["name"] = attendee["displayName"]

            if "responseStatus" in attendee:
                attendee_dict["status"] = attendee["responseStatus"]

            attendees.append(attendee_dict)

        result["attendees"] = attendees

    # Handle organizer
    if "organizer" in google_event:
        organizer = google_event["organizer"]
        organizer_dict = {"email": organizer.get("email", "")}

        if "name" in organizer:
            organizer_dict["name"] = organizer["name"]

        result["organizer"] = organizer_dict

    # Handle reminders
    if "reminders" in google_event and "overrides" in google_event["reminders"]:
        reminders = []
        for reminder in google_event["reminders"]["overrides"]:
            reminders.append({"minutes": reminder.get("minutes", 15)})

        result["reminders"] = reminders

    # Handle color
    if "colorId" in google_event:
        result["color_id"] = google_event["colorId"]

    # Handle transparency
    if "transparency" in google_event:
        result["transparency"] = google_event["transparency"]

    # Handle status
    if "status" in google_event:
        result["status"] = google_event["status"]

    # Handle conferenceData (meeting links)
    if (
        "conferenceData" in google_event
        and "entryPoints" in google_event["conferenceData"]
    ):
        for entry_point in google_event["conferenceData"]["entryPoints"]:
            if entry_point.get("entryPointType") == "video":
                result["meeting_link"] = entry_point.get("uri", "")
                break

    # Handle extended properties
    if "extendedProperties" in google_event:
        if "private" in google_event["extendedProperties"]:
            result["extended_properties"] = google_event["extendedProperties"][
                "private"
            ]

    # Extract calendar info if available
    if "calendar_id" in google_event:
        result["calendar_id"] = google_event["calendar_id"]

    if "calendar_name" in google_event:
        result["calendar_name"] = google_event["calendar_name"]

    return result


def generate_ics_file(
    events: List[Dict[str, Any]],
    filename: str = "calendar_export.ics",
    calendar_name: str = "Exported Calendar",
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """
    Generate an iCalendar .ics file from a list of events.

    Args:
        events: List of event dictionaries
        filename: Output filename
        calendar_name: Calendar name
        timezone: Calendar timezone

    Returns:
        Path to the generated .ics file
    """
    # Create calendar
    cal = create_calendar(name=calendar_name, timezone=timezone)

    # Add events
    for event_dict in events:
        # Check if this is already an iCalendar Event
        if isinstance(event_dict, Event):
            cal.add_component(event_dict)
        else:
            # Convert dictionary to iCalendar Event
            event = create_event_from_details(event_dict)
            cal.add_component(event)

    # Ensure output directory exists
    output_dir = os.path.dirname(filename)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Write to file
    with open(filename, "wb") as f:
        f.write(cal.to_ical())

    return filename


def parse_ics_file(ics_file: str) -> List[Dict[str, Any]]:
    """
    Parse an iCalendar .ics file into a list of event dictionaries.

    Args:
        ics_file: Path to .ics file

    Returns:
        List of event dictionaries
    """
    with open(ics_file, "rb") as f:
        cal = Calendar.from_ical(f.read())

    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            event_dict = event_to_dict(component)
            events.append(event_dict)

    return events
