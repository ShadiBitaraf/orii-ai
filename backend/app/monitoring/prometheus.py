"""
Prometheus metrics configuration for ORII.
Defines all metrics used across the application.
"""

from prometheus_client import Counter, Histogram, start_http_server
import os

# Configuration
PROM_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))

# LLM Metrics
llm_requests_total = Counter(
    "orii_llm_requests_total", "Total number of LLM API requests", ["status", "model"]
)

llm_request_duration = Histogram(
    "orii_llm_request_duration_seconds", "Time spent processing LLM requests", ["model"]
)

llm_token_usage = Counter(
    "orii_llm_token_usage_total",
    "Total number of tokens used in LLM requests",
    ["model", "type"],  # type can be 'prompt' or 'completion'
)

# Calendar API Metrics
calendar_requests_total = Counter(
    "orii_calendar_requests_total",
    "Total number of Google Calendar API requests",
    ["operation", "status"],
)

calendar_request_duration = Histogram(
    "orii_calendar_request_duration_seconds",
    "Time spent processing Calendar API requests",
    ["operation"],
)

# Cache Metrics
cache_hits = Counter(
    "orii_cache_hits_total", "Total number of cache hits", ["cache_type"]
)

cache_misses = Counter(
    "orii_cache_misses_total", "Total number of cache misses", ["cache_type"]
)

# User Metrics
user_sessions = Counter(
    "orii_user_sessions_total",
    "Total number of user sessions",
    ["type"],  # type can be 'cli', 'extension', etc.
)

user_queries = Counter(
    "orii_user_queries_total",
    "Total number of user queries",
    ["type", "status"],  # type can be 'calendar_query', 'event_creation', etc.
)


def start_metrics_server():
    """Start the Prometheus metrics server if not already running"""
    try:
        start_http_server(PROM_PORT)
        print(f"Prometheus metrics available on port {PROM_PORT}")
    except Exception as e:
        print(f"Warning: Could not start Prometheus server: {str(e)}")


def record_llm_request(
    status: str,
    model: str,
    duration: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
):
    """Record metrics for an LLM request"""
    llm_requests_total.labels(status=status, model=model).inc()
    llm_request_duration.labels(model=model).observe(duration)
    if prompt_tokens:
        llm_token_usage.labels(model=model, type="prompt").inc(prompt_tokens)
    if completion_tokens:
        llm_token_usage.labels(model=model, type="completion").inc(completion_tokens)


def record_calendar_request(operation: str, status: str, duration: float):
    """Record metrics for a calendar API request"""
    calendar_requests_total.labels(operation=operation, status=status).inc()
    calendar_request_duration.labels(operation=operation).observe(duration)


def record_cache_operation(cache_type: str, hit: bool):
    """Record metrics for cache operations"""
    if hit:
        cache_hits.labels(cache_type=cache_type).inc()
    else:
        cache_misses.labels(cache_type=cache_type).inc()


def record_user_session(session_type: str):
    """Record metrics for user sessions"""
    user_sessions.labels(type=session_type).inc()


def record_user_query(query_type: str, status: str):
    """Record metrics for user queries"""
    user_queries.labels(type=query_type, status=status).inc()
