"""
Google Calendar service functionality for the CLI application.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import SCOPES


class CalendarService:
    """Service class for interacting with Google Calendar API."""

    def __init__(self):
        """Initialize the CalendarService."""
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Google Calendar API."""
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if os.path.exists("token.json"):
            self.creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                self.creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(self.creds.to_json())

        self.service = build("calendar", "v3", credentials=self.creds)

    def get_events(
        self,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> List[Dict]:
        """Get events from Google Calendar.

        Args:
            time_min: Start time for event search
            time_max: End time for event search
            max_results: Maximum number of events to return
            single_events: Whether to expand recurring events
            order_by: How to order the results

        Returns:
            List of event dictionaries
        """
        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min.isoformat() if time_min else None,
                    timeMax=time_max.isoformat() if time_max else None,
                    maxResults=max_results,
                    singleEvents=single_events,
                    orderBy=order_by,
                )
                .execute()
            )

            return events_result.get("items", [])
        except HttpError as error:
            print(f"An error occurred: {error}")
            return []

    def create_event(
        self,
        summary: str,
        description: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        is_all_day: bool = False,
    ) -> Optional[Dict]:
        """Create a new event in Google Calendar.

        Args:
            summary: Event title
            description: Event description
            start_time: Event start time
            end_time: Event end time
            location: Event location
            attendees: List of attendee email addresses
            is_all_day: Whether this is an all-day event

        Returns:
            Created event dictionary or None if creation failed
        """
        event = {
            "summary": summary,
            "description": description,
            "location": location,
        }

        if is_all_day:
            event["start"] = {"date": start_time.strftime("%Y-%m-%d")}
            event["end"] = {"date": end_time.strftime("%Y-%m-%d")}
        else:
            event["start"] = {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC",
            }
            event["end"] = {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            }

        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        try:
            event = (
                self.service.events()
                .insert(
                    calendarId="primary",
                    body=event,
                    sendUpdates="all",
                )
                .execute()
            )
            return event
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None

    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        is_all_day: Optional[bool] = None,
    ) -> Optional[Dict]:
        """Update an existing event in Google Calendar.

        Args:
            event_id: ID of the event to update
            summary: New event title
            description: New event description
            start_time: New event start time
            end_time: New event end time
            location: New event location
            attendees: New list of attendee email addresses
            is_all_day: Whether this is an all-day event

        Returns:
            Updated event dictionary or None if update failed
        """
        try:
            event = (
                self.service.events()
                .get(
                    calendarId="primary",
                    eventId=event_id,
                )
                .execute()
            )

            if summary:
                event["summary"] = summary
            if description:
                event["description"] = description
            if location:
                event["location"] = location
            if attendees:
                event["attendees"] = [{"email": email} for email in attendees]

            if start_time and end_time:
                if is_all_day:
                    event["start"] = {"date": start_time.strftime("%Y-%m-%d")}
                    event["end"] = {"date": end_time.strftime("%Y-%m-%d")}
                else:
                    event["start"] = {
                        "dateTime": start_time.isoformat(),
                        "timeZone": "UTC",
                    }
                    event["end"] = {
                        "dateTime": end_time.isoformat(),
                        "timeZone": "UTC",
                    }

            updated_event = (
                self.service.events()
                .update(
                    calendarId="primary",
                    eventId=event_id,
                    body=event,
                    sendUpdates="all",
                )
                .execute()
            )
            return updated_event
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None

    def delete_event(self, event_id: str) -> bool:
        """Delete an event from Google Calendar.

        Args:
            event_id: ID of the event to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            self.service.events().delete(
                calendarId="primary",
                eventId=event_id,
                sendUpdates="all",
            ).execute()
            return True
        except HttpError as error:
            print(f"An error occurred: {error}")
            return False

    def get_event_details(self, event_id: str) -> Optional[Dict]:
        """Get details of a specific event.

        Args:
            event_id: ID of the event to get details for

        Returns:
            Event dictionary or None if event not found
        """
        try:
            event = (
                self.service.events()
                .get(
                    calendarId="primary",
                    eventId=event_id,
                )
                .execute()
            )
            return event
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None

    def get_upcoming_events(
        self,
        days_ahead: int = 7,
        max_results: int = 10,
    ) -> List[Dict]:
        """Get upcoming events for the next N days.

        Args:
            days_ahead: Number of days to look ahead
            max_results: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        now = datetime.utcnow()
        time_max = now + timedelta(days=days_ahead)
        return self.get_events(
            time_min=now,
            time_max=time_max,
            max_results=max_results,
        )

    def get_past_events(
        self,
        days_back: int = 7,
        max_results: int = 10,
    ) -> List[Dict]:
        """Get past events from the last N days.

        Args:
            days_back: Number of days to look back
            max_results: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        now = datetime.utcnow()
        time_min = now - timedelta(days=days_back)
        return self.get_events(
            time_min=time_min,
            time_max=now,
            max_results=max_results,
            order_by="startTime",
        )
