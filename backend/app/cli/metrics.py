"""
Prometheus metrics functionality for the CLI application.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server
from typing import Optional

from .config import PROM_PORT

# Define metrics
REQUEST_COUNT = Counter(
    "cli_request_total", "Total number of CLI requests", ["command", "status"]
)

REQUEST_LATENCY = Histogram(
    "cli_request_latency_seconds",
    "Request latency in seconds",
    ["command"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

CACHE_HITS = Counter(
    "cli_cache_hits_total", "Total number of cache hits", ["cache_type"]
)

CACHE_MISSES = Counter(
    "cli_cache_misses_total", "Total number of cache misses", ["cache_type"]
)

CACHE_SIZE = Gauge(
    "cli_cache_size_bytes", "Current size of the cache in bytes", ["cache_type"]
)

EVENT_COUNT = Counter(
    "cli_event_total", "Total number of calendar events", ["operation", "status"]
)

LLM_TOKENS = Counter(
    "cli_llm_tokens_total", "Total number of LLM tokens used", ["operation"]
)

LLM_ERRORS = Counter(
    "cli_llm_errors_total", "Total number of LLM errors", ["error_type"]
)


class Metrics:
    """Prometheus metrics manager for the CLI application."""

    def __init__(self):
        """Initialize the metrics manager."""
        self._start_server()

    def _start_server(self) -> None:
        """Start the Prometheus metrics server."""
        try:
            start_http_server(PROM_PORT)
        except Exception as e:
            print(f"Error starting metrics server: {e}")

    def record_request(
        self,
        command: str,
        status: str,
        latency: Optional[float] = None,
    ) -> None:
        """Record a CLI request.

        Args:
            command: The command that was executed
            status: The status of the request (success/failure)
            latency: The request latency in seconds
        """
        REQUEST_COUNT.labels(command=command, status=status).inc()
        if latency is not None:
            REQUEST_LATENCY.labels(command=command).observe(latency)

    def record_cache_access(
        self,
        cache_type: str,
        hit: bool,
    ) -> None:
        """Record a cache access.

        Args:
            cache_type: The type of cache being accessed
            hit: Whether it was a cache hit
        """
        if hit:
            CACHE_HITS.labels(cache_type=cache_type).inc()
        else:
            CACHE_MISSES.labels(cache_type=cache_type).inc()

    def record_cache_size(
        self,
        cache_type: str,
        size_bytes: int,
    ) -> None:
        """Record the current cache size.

        Args:
            cache_type: The type of cache
            size_bytes: The current size in bytes
        """
        CACHE_SIZE.labels(cache_type=cache_type).set(size_bytes)

    def record_event(
        self,
        operation: str,
        status: str,
    ) -> None:
        """Record a calendar event operation.

        Args:
            operation: The type of operation (create/update/delete)
            status: The status of the operation (success/failure)
        """
        EVENT_COUNT.labels(operation=operation, status=status).inc()

    def record_llm_tokens(
        self,
        operation: str,
        count: int,
    ) -> None:
        """Record LLM token usage.

        Args:
            operation: The type of operation
            count: The number of tokens used
        """
        LLM_TOKENS.labels(operation=operation).inc(count)

    def record_llm_error(
        self,
        error_type: str,
    ) -> None:
        """Record an LLM error.

        Args:
            error_type: The type of error that occurred
        """
        LLM_ERRORS.labels(error_type=error_type).inc()

    def reset_metrics(self) -> None:
        """Reset all metrics to their initial state."""
        REQUEST_COUNT._value.clear()
        REQUEST_LATENCY._value.clear()
        CACHE_HITS._value.clear()
        CACHE_MISSES._value.clear()
        CACHE_SIZE._value.clear()
        EVENT_COUNT._value.clear()
        LLM_TOKENS._value.clear()
        LLM_ERRORS._value.clear()
