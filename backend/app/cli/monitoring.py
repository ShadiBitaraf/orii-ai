"""
Performance monitoring for CLI operations.
"""

import time
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, Union, List

# Setup logger
logger = logging.getLogger(__name__)

# In-memory store for recent request metrics
# This could be replaced with a more persistent solution like a database
REQUEST_METRICS = {"calendar": [], "llm": []}

# Maximum number of metrics to keep in memory
MAX_METRICS = 100


def record_calendar_request(
    operation: str,
    success: bool,
    error: Optional[str] = None,
    duration: Optional[float] = None,
) -> None:
    """
    Record metrics for a calendar API request.

    Args:
        operation: Type of calendar operation (e.g., get_events, create_event)
        success: Whether the operation was successful
        error: Error message if operation failed
        duration: Duration of the operation in seconds
    """
    metric = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "success": success,
        "duration": duration or 0.0,
    }

    if error:
        metric["error"] = error

    # Add to metrics store
    REQUEST_METRICS["calendar"].append(metric)

    # Keep only the most recent metrics
    if len(REQUEST_METRICS["calendar"]) > MAX_METRICS:
        REQUEST_METRICS["calendar"] = REQUEST_METRICS["calendar"][-MAX_METRICS:]

    # Log the event
    if success:
        logger.info(f"Calendar operation '{operation}' completed in {duration:.3f}s")
    else:
        logger.error(
            f"Calendar operation '{operation}' failed in {duration:.3f}s: {error}"
        )


def record_llm_request(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    success: bool,
    error: Optional[str] = None,
    duration: Optional[float] = None,
) -> None:
    """
    Record metrics for an LLM API request.

    Args:
        model: LLM model name
        prompt_tokens: Number of tokens in the prompt
        completion_tokens: Number of tokens in the completion
        success: Whether the operation was successful
        error: Error message if operation failed
        duration: Duration of the operation in seconds
    """
    metric = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "success": success,
        "duration": duration or 0.0,
    }

    if error:
        metric["error"] = error

    # Add to metrics store
    REQUEST_METRICS["llm"].append(metric)

    # Keep only the most recent metrics
    if len(REQUEST_METRICS["llm"]) > MAX_METRICS:
        REQUEST_METRICS["llm"] = REQUEST_METRICS["llm"][-MAX_METRICS:]

    # Log the event
    if success:
        logger.info(
            f"LLM request to '{model}' completed in {duration:.3f}s ({prompt_tokens + completion_tokens} tokens)"
        )
    else:
        logger.error(f"LLM request to '{model}' failed in {duration:.3f}s: {error}")


def get_calendar_metrics(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent calendar request metrics.

    Args:
        limit: Maximum number of metrics to return

    Returns:
        List of calendar request metrics
    """
    return REQUEST_METRICS["calendar"][-limit:]


def get_llm_metrics(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent LLM request metrics.

    Args:
        limit: Maximum number of metrics to return

    Returns:
        List of LLM request metrics
    """
    return REQUEST_METRICS["llm"][-limit:]


def get_performance_summary() -> Dict[str, Any]:
    """
    Generate a summary of performance metrics.

    Returns:
        Dictionary with performance summary data
    """
    calendar_metrics = REQUEST_METRICS["calendar"]
    llm_metrics = REQUEST_METRICS["llm"]

    # Calculate calendar metrics
    calendar_success = sum(1 for m in calendar_metrics if m["success"])
    calendar_failure = len(calendar_metrics) - calendar_success
    calendar_avg_duration = sum(m["duration"] for m in calendar_metrics) / max(
        1, len(calendar_metrics)
    )

    # Calculate LLM metrics
    llm_success = sum(1 for m in llm_metrics if m["success"])
    llm_failure = len(llm_metrics) - llm_success
    llm_avg_duration = sum(m["duration"] for m in llm_metrics) / max(
        1, len(llm_metrics)
    )
    llm_total_tokens = sum(m["total_tokens"] for m in llm_metrics)

    # Build summary
    return {
        "timestamp": datetime.now().isoformat(),
        "calendar": {
            "total_requests": len(calendar_metrics),
            "success_rate": calendar_success / max(1, len(calendar_metrics)) * 100,
            "failure_count": calendar_failure,
            "avg_duration_ms": calendar_avg_duration * 1000,
        },
        "llm": {
            "total_requests": len(llm_metrics),
            "success_rate": llm_success / max(1, len(llm_metrics)) * 100,
            "failure_count": llm_failure,
            "avg_duration_ms": llm_avg_duration * 1000,
            "total_tokens": llm_total_tokens,
        },
    }
