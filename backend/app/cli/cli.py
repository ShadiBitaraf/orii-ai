"""
CLI interface for the application.
"""

import argparse
import sys
from typing import List, Optional

from .calendar_service import CalendarService
from .cache import Cache
from .commands import CommandHandlers
from .llm_service import LLMService
from .metrics import Metrics


def create_parser() -> argparse.ArgumentParser:
    """Create the command line argument parser.

    Returns:
        ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="CLI application for managing calendar events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Search events command
    search_parser = subparsers.add_parser("search", help="Search for calendar events")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of results to return",
    )

    # Create event command
    create_parser = subparsers.add_parser("create", help="Create a new calendar event")
    create_parser.add_argument("title", help="Event title")
    create_parser.add_argument(
        "--description",
        help="Event description",
    )
    create_parser.add_argument(
        "--start-time",
        help="Event start time (natural language)",
    )
    create_parser.add_argument(
        "--end-time",
        help="Event end time (natural language)",
    )
    create_parser.add_argument(
        "--location",
        help="Event location",
    )
    create_parser.add_argument(
        "--attendees",
        nargs="+",
        help="List of attendee email addresses",
    )
    create_parser.add_argument(
        "--all-day",
        action="store_true",
        help="Whether this is an all-day event",
    )

    # Update event command
    update_parser = subparsers.add_parser(
        "update", help="Update an existing calendar event"
    )
    update_parser.add_argument("event_id", help="ID of the event to update")
    update_parser.add_argument(
        "--title",
        help="New event title",
    )
    update_parser.add_argument(
        "--description",
        help="New event description",
    )
    update_parser.add_argument(
        "--start-time",
        help="New start time (natural language)",
    )
    update_parser.add_argument(
        "--end-time",
        help="New end time (natural language)",
    )
    update_parser.add_argument(
        "--location",
        help="New event location",
    )
    update_parser.add_argument(
        "--attendees",
        nargs="+",
        help="New list of attendee email addresses",
    )
    update_parser.add_argument(
        "--all-day",
        action="store_true",
        help="Whether this is an all-day event",
    )

    # Delete event command
    delete_parser = subparsers.add_parser("delete", help="Delete a calendar event")
    delete_parser.add_argument("event_id", help="ID of the event to delete")

    # Get event details command
    details_parser = subparsers.add_parser(
        "details", help="Get details of a calendar event"
    )
    details_parser.add_argument("event_id", help="ID of the event to get details for")

    # Get upcoming events command
    upcoming_parser = subparsers.add_parser(
        "upcoming", help="Get upcoming calendar events"
    )
    upcoming_parser.add_argument(
        "--days-ahead",
        type=int,
        default=7,
        help="Number of days to look ahead",
    )
    upcoming_parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of results to return",
    )

    # Get past events command
    past_parser = subparsers.add_parser("past", help="Get past calendar events")
    past_parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Number of days to look back",
    )
    past_parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of results to return",
    )

    # Cache commands
    cache_parser = subparsers.add_parser("cache", help="Cache management commands")
    cache_subparsers = cache_parser.add_subparsers(
        dest="cache_command", help="Available cache commands"
    )

    clear_cache_parser = cache_subparsers.add_parser("clear", help="Clear the cache")
    stats_cache_parser = cache_subparsers.add_parser(
        "stats", help="Get cache statistics"
    )

    return parser


def format_event(event: dict) -> str:
    """Format an event for display.

    Args:
        event: Event dictionary

    Returns:
        Formatted event string
    """
    lines = []
    lines.append(f"ID: {event.get('id', 'N/A')}")
    lines.append(f"Title: {event.get('summary', 'N/A')}")
    lines.append(f"Description: {event.get('description', 'N/A')}")
    lines.append(f"Location: {event.get('location', 'N/A')}")
    lines.append(
        f"Time: {format_datetime_range(event['start']['dateTime'], event['end']['dateTime'], event.get('allDay', False))}"
    )

    attendees = event.get("attendees", [])
    if attendees:
        lines.append("Attendees:")
        for attendee in attendees:
            lines.append(f"  - {attendee.get('email', 'N/A')}")

    return "\n".join(lines)


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 1

    try:
        # Initialize services
        calendar_service = CalendarService()
        cache = Cache()
        metrics = Metrics()
        llm_service = LLMService(cache, metrics)
        handlers = CommandHandlers(calendar_service, llm_service, cache, metrics)

        # Handle commands
        if parsed_args.command == "search":
            events = handlers.handle_search_events(
                query=parsed_args.query,
                max_results=parsed_args.max_results,
            )
            if events:
                for event in events:
                    print(format_event(event))
                    print("-" * 80)
            else:
                print("No events found.")

        elif parsed_args.command == "create":
            event = handlers.handle_create_event(
                title=parsed_args.title,
                description=parsed_args.description,
                start_time=parsed_args.start_time,
                end_time=parsed_args.end_time,
                location=parsed_args.location,
                attendees=parsed_args.attendees,
                is_all_day=parsed_args.all_day,
            )
            if event:
                print("Event created successfully:")
                print(format_event(event))
            else:
                print("Failed to create event.")

        elif parsed_args.command == "update":
            event = handlers.handle_update_event(
                event_id=parsed_args.event_id,
                title=parsed_args.title,
                description=parsed_args.description,
                start_time=parsed_args.start_time,
                end_time=parsed_args.end_time,
                location=parsed_args.location,
                attendees=parsed_args.attendees,
                is_all_day=parsed_args.all_day,
            )
            if event:
                print("Event updated successfully:")
                print(format_event(event))
            else:
                print("Failed to update event.")

        elif parsed_args.command == "delete":
            if handlers.handle_delete_event(parsed_args.event_id):
                print("Event deleted successfully.")
            else:
                print("Failed to delete event.")

        elif parsed_args.command == "details":
            event = handlers.handle_get_event_details(parsed_args.event_id)
            if event:
                print(format_event(event))
            else:
                print("Event not found.")

        elif parsed_args.command == "upcoming":
            events = handlers.handle_get_upcoming_events(
                days_ahead=parsed_args.days_ahead,
                max_results=parsed_args.max_results,
            )
            if events:
                for event in events:
                    print(format_event(event))
                    print("-" * 80)
            else:
                print("No upcoming events found.")

        elif parsed_args.command == "past":
            events = handlers.handle_get_past_events(
                days_back=parsed_args.days_back,
                max_results=parsed_args.max_results,
            )
            if events:
                for event in events:
                    print(format_event(event))
                    print("-" * 80)
            else:
                print("No past events found.")

        elif parsed_args.command == "cache":
            if parsed_args.cache_command == "clear":
                if handlers.handle_clear_cache():
                    print("Cache cleared successfully.")
                else:
                    print("Failed to clear cache.")
            elif parsed_args.cache_command == "stats":
                stats = handlers.handle_get_cache_stats()
                print(f"Cache size: {stats['size_bytes']} bytes")
                print(f"Number of keys: {stats['keys']}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
