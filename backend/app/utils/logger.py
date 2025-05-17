"""
Advanced logging configuration using Loguru.

This module configures Loguru as the main logging system for ORII with:
- Structured JSON logging to files
- Console logging with colored output (dev mode only)
- Asynchronous logging to a dedicated worker thread
- Log rotation and retention policy
- Environment-based configuration
"""

import os
import sys
import atexit
from pathlib import Path
from functools import wraps
import logging

from loguru import logger

# Create logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parents[3] / "app" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Default configuration that can be overridden by environment variables
DEFAULT_CONFIG = {
    "LOG_LEVEL": os.environ.get("ORII_LOG_LEVEL", "INFO"),
    "DEV_MODE": os.environ.get("ORII_DEV_MODE", "false").lower() in ("true", "1", "t"),
    "LOG_RETENTION": os.environ.get("ORII_LOG_RETENTION", "5"),
    "LOG_ROTATION": os.environ.get("ORII_LOG_ROTATION", "10 MB"),
    "JSON_LOGS": os.environ.get("ORII_JSON_LOGS", "true").lower() in ("true", "1", "t"),
}

# Remove all default handlers
logger.remove()


# Configure Loguru for standard library logging compatibility
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where this was logged
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(config=None):
    """Initialize logging configuration"""
    # Use provided config or default
    cfg = config or DEFAULT_CONFIG
    log_level = cfg["LOG_LEVEL"].upper()
    dev_mode = cfg["DEV_MODE"]
    log_retention = int(cfg["LOG_RETENTION"])
    log_rotation = cfg["LOG_ROTATION"]

    # Configure file logging
    log_file = LOGS_DIR / "orii.log"

    # Add file handler with rotation and retention policy
    logger.add(
        str(log_file),
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=log_rotation,
        retention=log_retention,
        enqueue=True,
        backtrace=True,
        diagnose=True,
        compression="zip",
    )

    # Configure console output only in dev mode
    if dev_mode:
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>",
            level=log_level,
            colorize=True,
            enqueue=True,
        )

    # Intercept standard library logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Register cleanup handler
    atexit.register(logger.complete)

    return logger


# Initialize logger
logger = setup_logging()


def get_logger(name=None, module=None):
    """Get a named logger"""
    if name and module:
        return logger.bind(name=name, module=module)
    elif name:
        return logger.bind(name=name)
    elif module:
        return logger.bind(module=module)
    return logger


def with_logger(function):
    """Decorator that provides a logger to the wrapped function"""

    @wraps(function)
    def wrapper(*args, **kwargs):
        kwargs["logger"] = logger.bind(function=function.__name__)
        return function(*args, **kwargs)

    return wrapper
