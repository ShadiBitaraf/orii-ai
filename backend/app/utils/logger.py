"""
Logging Utility
Provides consistent logging setup for the entire application
"""

import logging
import sys
import os
from datetime import datetime
import importlib.util

# Handle the import error gracefully
try:
    from backend.app.core.config import get_settings

    settings = get_settings()
except ImportError:
    # Create a simple settings object with defaults
    class SimpleSettings:
        ENV = "development"

    settings = SimpleSettings()

# Create logs directory if it doesn't exist
os.makedirs("app/logs", exist_ok=True)

# Get current date for log filename
current_date = datetime.now().strftime("%Y-%m-%d")
log_filename = f"app/logs/orii-{settings.ENV}-{current_date}.log"


# Configure logging
def setup_logger(name: str = "app", console_output: bool = True, log_file: str = None):
    """Setup and return a configured logger instance

    Args:
        name: Name of the logger
        console_output: Whether to output logs to console
        log_file: Custom log file path. If None, uses the default path.

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if handlers aren't already set up
    if not logger.handlers:
        logger.setLevel(
            logging.DEBUG if settings.ENV == "development" else logging.INFO
        )

        # Use custom log file if provided
        file_path = log_file if log_file else log_filename

        # Console handler (only if console_output is True)
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(
                logging.DEBUG if settings.ENV == "development" else logging.INFO
            )
            console_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        # File handler
        try:
            # Make sure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            file_handler = logging.FileHandler(file_path)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # If we can't write to the file, log to console as a fallback
            fallback_handler = logging.StreamHandler(sys.stderr)
            fallback_handler.setLevel(logging.WARNING)
            fallback_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            fallback_handler.setFormatter(fallback_formatter)
            logger.addHandler(fallback_handler)

            # Log the error
            logger.warning(f"Could not create log file at {file_path}: {e}")

    return logger


# Add this function to make it compatible with existing code
def get_logger(name: str = "app"):
    """Get a logger with the given name (alias for setup_logger)"""
    return setup_logger(name)


# Default app logger
app_logger = setup_logger("app")
