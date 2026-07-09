# Google API calls
# 3
# "go fetch events from Google API for this date range"

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Note: A class makes sense when you need to store state across multiple method calls. retrieve_cal_data doesnt need to remember anything between calls. it just take inputs and return outputs. unlike cache that needed to keep track of cached_data and ttl_mins.
def retrieve_cal_data(creds, start_date, end_date):
    service = build("calendar", "v3", credentials=creds)
    try:
        events_result = (
            service.events()
            .list(
                calendarId="primary",  # TODO: for Orii V2, call calendarList().list() first to get all calendar IDs, then loop through them. for users with multiple calendars to scan.
                timeMin=start_date,
                timeMax=end_date,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get(
            "items", []
        )  # Note: this line says "either extract the events list from the 'items' key or return an empty list if empty."

    except HttpError as error:
        print(f"An error occurred: {error}")
        return None
