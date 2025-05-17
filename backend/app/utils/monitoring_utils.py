"""
Monitoring utilities for performance tracking across the application.
"""

import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Metrics storage
calendar_metrics = {
    "requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_duration": 0,
    "request_history": [],  # List of (operation, success, duration, timestamp)
}

llm_metrics = {
    "requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_tokens": 0,
    "total_duration": 0,
    "request_history": [],  # List of (operation, success, tokens, duration, timestamp)
}


def record_calendar_request(
    operation: str, success: bool, error: Optional[str], duration: float
) -> None:
    """
    Record metrics for a calendar API request.

    Args:
        operation: The operation that was performed
        success: Whether the operation was successful
        error: Error message if operation failed
        duration: Time taken for the operation in seconds
    """
    calendar_metrics["requests"] += 1
    if success:
        calendar_metrics["successful_requests"] += 1
    else:
        calendar_metrics["failed_requests"] += 1
        logger.error(f"Calendar operation '{operation}' failed: {error}")

    calendar_metrics["total_duration"] += duration
    calendar_metrics["request_history"].append(
        (operation, success, duration, time.time())
    )

    # Keep history limited to last 100 operations to avoid memory issues
    if len(calendar_metrics["request_history"]) > 100:
        calendar_metrics["request_history"].pop(0)

    logger.debug(
        f"Calendar operation '{operation}' {'succeeded' if success else 'failed'} in {duration:.2f}s"
    )


def record_llm_request(
    operation: str, success: bool, tokens: int, duration: float
) -> None:
    """
    Record metrics for an LLM API request.

    Args:
        operation: The operation that was performed
        success: Whether the operation was successful
        tokens: Number of tokens used
        duration: Time taken for the operation in seconds
    """
    llm_metrics["requests"] += 1
    if success:
        llm_metrics["successful_requests"] += 1
    else:
        llm_metrics["failed_requests"] += 1

    llm_metrics["total_tokens"] += tokens
    llm_metrics["total_duration"] += duration
    llm_metrics["request_history"].append(
        (operation, success, tokens, duration, time.time())
    )

    # Keep history limited to last 100 operations to avoid memory issues
    if len(llm_metrics["request_history"]) > 100:
        llm_metrics["request_history"].pop(0)

    logger.debug(
        f"LLM operation '{operation}' {'succeeded' if success else 'failed'} "
        f"using {tokens} tokens in {duration:.2f}s"
    )


def get_calendar_metrics() -> Dict[str, Any]:
    """
    Get metrics for calendar operations.

    Returns:
        Dictionary with calendar metrics
    """
    avg_duration = (
        calendar_metrics["total_duration"] / calendar_metrics["requests"]
        if calendar_metrics["requests"] > 0
        else 0
    )
    success_rate = (
        calendar_metrics["successful_requests"] / calendar_metrics["requests"] * 100
        if calendar_metrics["requests"] > 0
        else 0
    )

    return {
        "requests": calendar_metrics["requests"],
        "successful_requests": calendar_metrics["successful_requests"],
        "failed_requests": calendar_metrics["failed_requests"],
        "success_rate": success_rate,
        "avg_duration": avg_duration,
        "total_duration": calendar_metrics["total_duration"],
    }


def get_llm_metrics() -> Dict[str, Any]:
    """
    Get metrics for LLM operations.

    Returns:
        Dictionary with LLM metrics
    """
    avg_duration = (
        llm_metrics["total_duration"] / llm_metrics["requests"]
        if llm_metrics["requests"] > 0
        else 0
    )
    avg_tokens = (
        llm_metrics["total_tokens"] / llm_metrics["requests"]
        if llm_metrics["requests"] > 0
        else 0
    )
    success_rate = (
        llm_metrics["successful_requests"] / llm_metrics["requests"] * 100
        if llm_metrics["requests"] > 0
        else 0
    )

    return {
        "requests": llm_metrics["requests"],
        "successful_requests": llm_metrics["successful_requests"],
        "failed_requests": llm_metrics["failed_requests"],
        "success_rate": success_rate,
        "total_tokens": llm_metrics["total_tokens"],
        "avg_tokens": avg_tokens,
        "avg_duration": avg_duration,
        "total_duration": llm_metrics["total_duration"],
    }


def reset_metrics() -> None:
    """
    Reset all metrics.
    """
    global calendar_metrics, llm_metrics

    calendar_metrics = {
        "requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "total_duration": 0,
        "request_history": [],
    }

    llm_metrics = {
        "requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "total_tokens": 0,
        "total_duration": 0,
        "request_history": [],
    }

    logger.info("All metrics have been reset")
