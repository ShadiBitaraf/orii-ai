"""
CLI command handlers for the application.
"""

import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone

from ..core.calendar.calendar_service import (
    get_calendar_service,
    get_events,
    get_event,
    get_calendar_timezone,
)
from ..utils.cache_utils import get_cached_data, set_cached_data, delete_cached_data
from ..core.llm.llm_service import LLMService
from ..utils.metrics_utils import Metrics
from ..core.time.time_manager import (
    parse_time_range,
    parse_natural_language_datetime,
    format_datetime_range,
)


class CommandHandlers:
    """Handlers for CLI commands."""

    def __init__(
        self,
        llm_service: LLMService,
        metrics: Metrics,
        credentials_dict=None,
    ):
        """Initialize the command handlers.

        Args:
            llm_service: LLM service instance
            metrics: Metrics instance
            credentials_dict: Optional dictionary with Google credentials
        """
        self.calendar_service = get_calendar_service(credentials_dict)
        self.llm_service = llm_service
        self.metrics = metrics

    def handle_search_events(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict]:
        """Handle the search events command.

        Args:
            query: Search query
            max_results: Maximum number of results to return

        Returns:
            List of matching events
        """
        start_time = time.time()
        try:
            # Parse time range from query
            time_info = parse_time_range(query)
            is_past = time_info["is_past"]
            days_range = time_info["days_range"]
            reverse_chronological = time_info["reverse_chronological"]
            specific_date = time_info.get("specific_date")

            # Get events based on time range
            if specific_date:
                time_min = specific_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                time_max = specific_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            else:
                now = datetime.utcnow()
                if is_past:
                    time_max = now
                    time_min = now - timedelta(days=days_range)
                else:
                    time_min = now
                    time_max = now + timedelta(days=days_range)

            events = get_events(
                self.calendar_service,
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
                orderby="startTime" if not reverse_chronological else "startTime",
            )

            # Filter events based on query
            if query and not specific_date:
                # Use LLM to classify if event matches query
                filtered_events = []
                for event in events:
                    event_text = (
                        f"{event.get('summary', '')} {event.get('description', '')}"
                    )
                    is_match = (
                        self.llm_service.classify(
                            event_text,
                            ["match", "no_match"],
                            temperature=0.1,
                        )
                        == "match"
                    )
                    if is_match:
                        filtered_events.append(event)
                events = filtered_events

            # Record metrics
            self.metrics.record_request(
                "search_events", "success", time.time() - start_time
            )
            self.metrics.record_event("search", "success")

            return events
        except Exception as e:
            self.metrics.record_request(
                "search_events", "failure", time.time() - start_time
            )
            self.metrics.record_event("search", "failure")
            raise

    def handle_create_event(
        self,
        title: str,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        is_all_day: bool = False,
    ) -> Optional[Dict]:
        """Handle the create event command.

        Args:
            title: Event title
            description: Event description
            start_time: Start time string
            end_time: End time string
            location: Event location
            attendees: List of attendee email addresses
            is_all_day: Whether this is an all-day event

        Returns:
            Created event or None if creation failed
        """
        start_time = time.time()
        try:
            # Parse times if provided
            if start_time:
                start_dt = parse_natural_language_datetime(start_time)["start_datetime"]
            else:
                start_dt = datetime.now()

            if end_time:
                end_dt = parse_natural_language_datetime(end_time)["start_datetime"]
            else:
                end_dt = start_dt + timedelta(hours=1)

            # Create event
            event = self.calendar_service.create_event(
                summary=title,
                description=description,
                start_time=start_dt,
                end_time=end_dt,
                location=location,
                attendees=attendees,
                is_all_day=is_all_day,
            )

            # Record metrics
            self.metrics.record_request(
                "create_event", "success", time.time() - start_time
            )
            self.metrics.record_event("create", "success")

            return event
        except Exception as e:
            self.metrics.record_request(
                "create_event", "failure", time.time() - start_time
            )
            self.metrics.record_event("create", "failure")
            raise

    def handle_update_event(
        self,
        event_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        is_all_day: Optional[bool] = None,
    ) -> Optional[Dict]:
        """Handle the update event command.

        Args:
            event_id: ID of the event to update
            title: New event title
            description: New event description
            start_time: New start time string
            end_time: New end time string
            location: New event location
            attendees: New list of attendee email addresses
            is_all_day: Whether this is an all-day event

        Returns:
            Updated event or None if update failed
        """
        start_time = time.time()
        try:
            # Parse times if provided
            start_dt = None
            end_dt = None
            if start_time:
                start_dt = parse_natural_language_datetime(start_time)["start_datetime"]
            if end_time:
                end_dt = parse_natural_language_datetime(end_time)["start_datetime"]

            # Update event
            event = self.calendar_service.update_event(
                event_id=event_id,
                summary=title,
                description=description,
                start_time=start_dt,
                end_time=end_dt,
                location=location,
                attendees=attendees,
                is_all_day=is_all_day,
            )

            # Record metrics
            self.metrics.record_request(
                "update_event", "success", time.time() - start_time
            )
            self.metrics.record_event("update", "success")

            return event
        except Exception as e:
            self.metrics.record_request(
                "update_event", "failure", time.time() - start_time
            )
            self.metrics.record_event("update", "failure")
            raise

    def handle_delete_event(
        self,
        event_id: str,
    ) -> bool:
        """Handle the delete event command.

        Args:
            event_id: ID of the event to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        start_time = time.time()
        try:
            success = self.calendar_service.delete_event(event_id)

            # Record metrics
            self.metrics.record_request(
                "delete_event",
                "success" if success else "failure",
                time.time() - start_time,
            )
            self.metrics.record_event("delete", "success" if success else "failure")

            return success
        except Exception as e:
            self.metrics.record_request(
                "delete_event", "failure", time.time() - start_time
            )
            self.metrics.record_event("delete", "failure")
            raise

    def handle_get_event_details(
        self,
        event_id: str,
    ) -> Optional[Dict]:
        """Handle the get event details command.

        Args:
            event_id: ID of the event to get details for

        Returns:
            Event dictionary or None if event was not found
        """
        start_time = time.time()
        try:
            event = get_event(self.calendar_service, event_id)

            # Record metrics
            self.metrics.record_request(
                "get_event_details",
                "success" if event else "failure",
                time.time() - start_time,
            )

            return event
        except Exception as e:
            self.metrics.record_request(
                "get_event_details", "failure", time.time() - start_time
            )
            raise

    def handle_get_upcoming_events(
        self,
        days_ahead: int = 7,
        max_results: int = 10,
    ) -> List[Dict]:
        """Handle the get upcoming events command.

        Args:
            days_ahead: Number of days to look ahead
            max_results: Maximum number of results to return

        Returns:
            List of upcoming events
        """
        start_time = time.time()
        try:
            # Calculate time range
            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days_ahead)).isoformat()

            # Get events
            events = get_events(
                self.calendar_service,
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
            )

            # Record metrics
            self.metrics.record_request(
                "get_upcoming_events", "success", time.time() - start_time
            )

            return events
        except Exception as e:
            self.metrics.record_request(
                "get_upcoming_events", "failure", time.time() - start_time
            )
            raise

    def handle_get_past_events(
        self,
        days_back: int = 7,
        max_results: int = 10,
    ) -> List[Dict]:
        """Handle the get past events command.

        Args:
            days_back: Number of days to look back
            max_results: Maximum number of results to return

        Returns:
            List of past events
        """
        start_time = time.time()
        try:
            # Calculate time range
            now = datetime.now(timezone.utc)
            time_max = now.isoformat()
            time_min = (now - timedelta(days=days_back)).isoformat()

            # Get events
            events = get_events(
                self.calendar_service,
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
                orderby="startTime desc",
            )

            # Record metrics
            self.metrics.record_request(
                "get_past_events", "success", time.time() - start_time
            )

            return events
        except Exception as e:
            self.metrics.record_request(
                "get_past_events", "failure", time.time() - start_time
            )
            raise

    def handle_clear_cache(
        self,
    ) -> bool:
        """Handle the clear cache command.

        Returns:
            True if cache was cleared successfully, False otherwise
        """
        start_time = time.time()
        try:
            from ..utils.cache_utils import clear_cache, get_cache_stats

            clear_cache()  # This function doesn't return a value in the new implementation
            success = True

            # Record metrics
            self.metrics.record_request(
                "clear_cache",
                "success" if success else "failure",
                time.time() - start_time,
            )

            return success
        except Exception as e:
            self.metrics.record_request(
                "clear_cache", "failure", time.time() - start_time
            )
            raise

    def handle_get_cache_stats(
        self,
    ) -> Dict[str, Any]:
        """Handle the get cache stats command.

        Returns:
            Dictionary with cache statistics
        """
        start_time = time.time()
        try:
            from ..utils.cache_utils import get_cache_stats

            stats = get_cache_stats()

            # Record metrics
            self.metrics.record_request(
                "get_cache_stats", "success", time.time() - start_time
            )

            return stats
        except Exception as e:
            self.metrics.record_request(
                "get_cache_stats", "failure", time.time() - start_time
            )
            raise
