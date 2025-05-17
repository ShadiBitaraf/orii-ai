#!/usr/bin/env python3
"""
ORII Log Monitor
---------------
A development tool to monitor, filter, and display logs from the ORII application
in real-time with color formatting.
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
import re
from datetime import datetime
import signal
import curses
from curses import wrapper
import threading

# ANSI color codes for terminal output
COLORS = {
    "TRACE": "\033[37m",  # White
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "SUCCESS": "\033[32;1m",  # Bright Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[41m",  # Red Background
    "reset": "\033[0m",
    "bold": "\033[1m",
    "timestamp": "\033[90m",  # Gray
    "module": "\033[35m",  # Magenta
}

# Default log directory
LOGS_DIR = Path(__file__).parent / "app" / "logs"


def format_log_entry(entry, is_json=True):
    """Format a log entry with colors."""
    try:
        if is_json:
            try:
                data = json.loads(entry)
                level = data.get("level", "INFO")
                message = data.get("message", "")
                timestamp = data.get("timestamp", "")
                module = data.get("module", "")
                function = data.get("function", "")
                line = data.get("line", "")

                module_info = f"{module}:{function}:{line}" if module else ""

                return (
                    f"{COLORS['timestamp']}{timestamp}{COLORS['reset']} "
                    f"{COLORS.get(level, COLORS['INFO'])}{level:8}{COLORS['reset']} "
                    f"{COLORS['module']}{module_info}{COLORS['reset']} "
                    f"{COLORS.get(level, COLORS['INFO'])}{message}{COLORS['reset']}"
                )
            except json.JSONDecodeError:
                # Not JSON, fall back to simple formatting
                return format_log_entry(entry, is_json=False)
        else:
            # Simple format for non-JSON logs
            # Try to extract level from the log entry
            level_match = re.search(
                r"\|\s*(TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL)\s*\|", entry
            )
            level = level_match.group(1) if level_match else "INFO"

            # Add color to the level in the log
            colored_entry = re.sub(
                r"\|\s*(TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL)\s*\|",
                lambda m: f"| {COLORS.get(m.group(1), COLORS['INFO'])}{m.group(1):8}{COLORS['reset']} |",
                entry,
            )

            # Color the timestamp
            colored_entry = re.sub(
                r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",
                lambda m: f"{COLORS['timestamp']}{m.group(0)}{COLORS['reset']}",
                colored_entry,
            )

            return colored_entry

    except Exception as e:
        return (
            f"{COLORS['ERROR']}Error formatting log: {str(e)}{COLORS['reset']}\n{entry}"
        )


def tail_log(log_file, level_filter=None, module_filter=None):
    """Tail a log file and display entries matching filters in real-time."""
    print(f"\n{COLORS['bold']}ORII Log Monitor{COLORS['reset']}")
    print(f"Watching: {log_file}")
    if level_filter:
        print(f"Level filter: {level_filter}")
    if module_filter:
        print(f"Module filter: {module_filter}")
    print("\n" + "-" * 80 + "\n")

    # Convert filter strings to lowercase for case-insensitive matching
    level_filter_lower = level_filter.lower() if level_filter else None
    module_filter_lower = module_filter.lower() if module_filter else None

    # Get the file size to start at the end
    try:
        file_size = os.path.getsize(log_file)
    except OSError:
        file_size = 0

    with open(log_file, "r") as f:
        # Move to the end of the file
        f.seek(file_size)

        while True:
            line = f.readline()
            if line:
                # Check if line matches filters
                should_display = True

                # Parse log entry if it's JSON
                try:
                    log_data = json.loads(line)
                    if (
                        level_filter_lower
                        and log_data.get("level", "").lower() != level_filter_lower
                    ):
                        should_display = False
                    if module_filter_lower and not (
                        (log_data.get("module", "").lower() == module_filter_lower)
                        or (log_data.get("name", "").lower() == module_filter_lower)
                    ):
                        should_display = False
                except json.JSONDecodeError:
                    # Not JSON, do simple text-based filtering
                    if level_filter_lower and level_filter_lower not in line.lower():
                        should_display = False
                    if module_filter_lower and module_filter_lower not in line.lower():
                        should_display = False

                if should_display:
                    formatted_line = format_log_entry(line)
                    print(formatted_line)
                    sys.stdout.flush()
            else:
                time.sleep(0.1)  # Sleep briefly when no new data


def list_logs():
    """List available log files with their sizes and modification times."""
    if not LOGS_DIR.exists():
        print(f"Log directory {LOGS_DIR} does not exist.")
        return

    log_files = list(LOGS_DIR.glob("*.log"))
    if not log_files:
        print(f"No log files found in {LOGS_DIR}.")
        return

    print(f"\n{COLORS['bold']}Available Log Files:{COLORS['reset']}")
    print(f"{'File Name':<30} {'Size':<10} {'Last Modified':<20}")
    print("-" * 60)

    for log_file in sorted(log_files, key=lambda x: os.path.getmtime(x), reverse=True):
        size = os.path.getsize(log_file)
        size_str = (
            f"{size / 1024:.1f} KB"
            if size < 1024 * 1024
            else f"{size / (1024 * 1024):.1f} MB"
        )
        mod_time = datetime.fromtimestamp(os.path.getmtime(log_file)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        print(f"{log_file.name:<30} {size_str:<10} {mod_time:<20}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="ORII Log Monitor")
    parser.add_argument(
        "-f",
        "--file",
        help="Specific log file to monitor (defaults to orii.log)",
        default="orii.log",
    )
    parser.add_argument(
        "-l",
        "--level",
        help="Filter logs by level (e.g., DEBUG, INFO, ERROR)",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        default=None,
    )
    parser.add_argument(
        "-m", "--module", help="Filter logs by module name", default=None
    )
    parser.add_argument("--list", help="List available log files", action="store_true")
    parser.add_argument(
        "--clear", help="Clear the terminal before starting", action="store_true"
    )

    return parser.parse_args()


def main():
    # Parse command line arguments
    args = parse_args()

    # Clear terminal if requested
    if args.clear:
        os.system("cls" if os.name == "nt" else "clear")

    # List logs if requested
    if args.list:
        list_logs()
        return

    # Determine log file path
    log_file = args.file
    if not os.path.isabs(log_file):
        log_file = LOGS_DIR / log_file

    # Ensure log file exists
    if not os.path.exists(log_file):
        print(f"Log file {log_file} does not exist.")
        print(f"Available logs in {LOGS_DIR}:")
        list_logs()
        return

    try:
        # Start monitoring logs
        tail_log(log_file, args.level, args.module)
    except KeyboardInterrupt:
        print(f"\n{COLORS['bold']}Log monitoring stopped.{COLORS['reset']}")
        return


if __name__ == "__main__":
    main()
