"""
Logging Utility
Provides consistent logging setup for the entire application
"""

import logging
import sys
import os
from datetime import datetime
from app.core.config import get_settings

settings = get_settings()

# Create logs directory if it doesn't exist
os.makedirs("app/logs", exist_ok=True)

# Get current date for log filename
current_date = datetime.now().strftime("%Y-%m-%d")
log_filename = f"app/logs/orii-{settings.ENV}-{current_date}.log"


# Configure logging
def setup_logger(name: str = "app"):
    """Setup and return a configured logger instance"""
    logger = logging.getLogger(name)

    # Only configure if handlers aren't already set up
    if not logger.handlers:
        logger.setLevel(
            logging.DEBUG if settings.ENV == "development" else logging.INFO
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(
            logging.DEBUG if settings.ENV == "development" else logging.INFO
        )
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # File handler
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # Add handlers
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger


# Default app logger
app_logger = setup_logger("app")
