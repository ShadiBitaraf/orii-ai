"""
Monitoring module that re-exports from utils/monitoring_utils.py.
This avoids duplicate monitoring implementations and circular imports.
"""

# Re-export the monitoring functions from utils
from ..utils.monitoring_utils import (
    record_calendar_request,
    record_llm_request,
    get_calendar_metrics,
    get_llm_metrics,
    reset_metrics,
)

__all__ = [
    "record_calendar_request",
    "record_llm_request",
    "get_calendar_metrics",
    "get_llm_metrics",
    "reset_metrics",
]
