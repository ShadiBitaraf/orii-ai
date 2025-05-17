"""
Cache module that re-exports from utils/cache_utils.py.
This avoids duplicate cache implementations and circular imports.
"""

# Re-export all functions and classes from cache_utils
from ..utils.cache_utils import (
    get_cached_data,
    set_cached_data,
    set_local_cache,
    delete_cached_data,
    clear_cache,
    get_cache_stats,
    CacheKeyBuilder,
    LOCAL_CACHE,
    REDIS_AVAILABLE,
    DEFAULT_EXPIRATION,
    CACHE_TTL,
    LLM_CACHE_SIZE,
)

# Export all symbols for star imports
__all__ = [
    "get_cached_data",
    "set_cached_data",
    "set_local_cache",
    "delete_cached_data",
    "clear_cache",
    "get_cache_stats",
    "CacheKeyBuilder",
    "LOCAL_CACHE",
    "REDIS_AVAILABLE",
    "DEFAULT_EXPIRATION",
    "CACHE_TTL",
    "LLM_CACHE_SIZE",
]
