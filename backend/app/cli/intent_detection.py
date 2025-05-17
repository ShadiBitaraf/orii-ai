"""
Intent detection module that re-exports from core/intent/intent_detection.py.
This avoids circular imports.
"""

# Re-export all functions and constants from core/intent/intent_detection
from ..core.intent.intent_detection import (
    determine_query_intent,
    classify_intent_with_llm,
    classify_intent_with_rules,
    extract_search_terms,
    rule_based_intent_detection,
)

# Export all symbols for star imports
__all__ = [
    "determine_query_intent",
    "classify_intent_with_llm",
    "classify_intent_with_rules",
    "extract_search_terms",
    "rule_based_intent_detection",
]
