"""
Main CLI interface for the calendar assistant.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Import functionality from modular files
from .query_processor import (
    process_query,
    get_visible_calendars,
    get_calendar_list_response,
)
from .intent_processor import process_intent
from .event_retrieval import (
    get_events_in_range,
    search_events,
    get_upcoming_events,
    get_past_events,
)
from .calendar_service import get_calendar_service
from .monitoring import record_calendar_request, get_calendar_request_stats

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def get_credentials() -> Credentials:
    """Get or refresh Google Calendar API credentials.

    Returns:
        Credentials object for the Google Calendar API
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def json_serialize(obj):
    """Helper function to make result dictionary JSON serializable

    Args:
        obj: The object to serialize

    Returns:
        JSON serializable version of the object
    """
    if isinstance(obj, dict):
        return {k: json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_serialize(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj


def main():
    """Main entry point for the CLI application."""
    # Check for credentials
    creds = get_credentials()
    if not creds:
        logger.error("Failed to get credentials")
        return 1

    # Simple command-line interface
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = process_query(query)
        print(json_serialize(result))
        return 0
    else:
        print("Usage: python -m backend.app.cli <query>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
