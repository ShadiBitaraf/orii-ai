"""
Metrics module that re-exports from utils/metrics_utils.py.
This avoids duplicate Prometheus metric registration.
"""

# Re-export the Metrics class from utils
from ..utils.metrics_utils import Metrics

# Re-export any necessary constants or functions
from ..utils.metrics_utils import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    CACHE_HITS,
    CACHE_MISSES,
    CACHE_SIZE,
    EVENT_COUNT,
    LLM_TOKENS,
    LLM_ERRORS,
)

__all__ = [
    "Metrics",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "CACHE_HITS",
    "CACHE_MISSES",
    "CACHE_SIZE",
    "EVENT_COUNT",
    "LLM_TOKENS",
    "LLM_ERRORS",
]
