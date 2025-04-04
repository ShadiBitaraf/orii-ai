"""
Cache utilities for reducing API calls and improving performance.
"""

import redis
import time
import threading
import json
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta

from .config import REDIS_URL, CACHE_TTL, LLM_CACHE_SIZE

# Setup logger
logger = logging.getLogger(__name__)

# In-memory cache for faster access to frequently used data
LOCAL_CACHE = {}

# Cache lock for thread safety
cache_lock = threading.RLock()

# Redis connection
try:
    redis_client = redis.from_url(REDIS_URL)
    REDIS_AVAILABLE = True
    logger.info("Redis cache initialized")
except Exception as e:
    REDIS_AVAILABLE = False
    logger.warning(f"Redis cache not available: {e}. Using local cache only.")

# Constants
DEFAULT_EXPIRATION = 300  # 5 minutes


class CacheKeyBuilder:
    """Helper class to build standardized cache keys."""

    @staticmethod
    def llm_response_key(prompt: str, model: str) -> str:
        """
        Generate a key for an LLM response.

        Args:
            prompt: The prompt text
            model: The LLM model name

        Returns:
            Cache key string
        """
        import hashlib

        # Hash the prompt to avoid long keys and special characters
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        return f"llm:response:{model}:{prompt_hash}"

    @staticmethod
    def calendar_events_key(
        calendar_id: str, time_min: str, time_max: str, query: str = ""
    ) -> str:
        """
        Generate a key for calendar events.

        Args:
            calendar_id: Calendar ID
            time_min: Start time for events
            time_max: End time for events
            query: Optional search query

        Returns:
            Cache key string
        """
        import hashlib

        # Hash the parameters to create a compact key
        params = f"{calendar_id}:{time_min}:{time_max}:{query}"
        params_hash = hashlib.md5(params.encode()).hexdigest()
        return f"calendar:events:{params_hash}"

    @staticmethod
    def calendar_event_key(calendar_id: str, event_id: str) -> str:
        """
        Generate a key for a specific calendar event.

        Args:
            calendar_id: Calendar ID
            event_id: Event ID

        Returns:
            Cache key string
        """
        return f"calendar:event:{calendar_id}:{event_id}"

    @staticmethod
    def calendar_list_key() -> str:
        """
        Generate a key for the calendar list.

        Returns:
            Cache key string
        """
        return "calendar:list"

    @staticmethod
    def calendar_timezone_key(calendar_id: str) -> str:
        """
        Generate a key for a calendar's timezone.

        Args:
            calendar_id: Calendar ID

        Returns:
            Cache key string
        """
        return f"calendar:timezone:{calendar_id}"


def get_cached_data(key: str) -> Optional[Any]:
    """
    Retrieve data from cache if it exists and hasn't expired.
    Uses local memory cache first, then falls back to Redis if available.

    Args:
        key: Cache key to retrieve

    Returns:
        Cached data or None if not found or expired
    """
    # First check local memory cache for faster access
    with cache_lock:
        if key in LOCAL_CACHE:
            entry = LOCAL_CACHE[key]
            # Check if entry has expired
            if entry["expiry"] > time.time() or entry["expiry"] == 0:
                logger.debug(f"Local cache hit for key: {key}")
                return entry["data"]
            else:
                # Remove expired entry
                logger.debug(f"Local cache expired for key: {key}")
                del LOCAL_CACHE[key]

    # If not in local cache, try Redis if available
    if REDIS_AVAILABLE:
        try:
            data = redis_client.get(key)
            if data:
                # Deserialize the data from JSON
                result = json.loads(data)
                # Also update local cache for faster future access
                set_local_cache(key, result, redis_client.ttl(key))
                logger.debug(f"Redis cache hit for key: {key}")
                return result
        except Exception as e:
            logger.error(f"Redis error retrieving key {key}: {e}")

    logger.debug(f"Cache miss for key: {key}")
    return None


def set_cached_data(key: str, data: Any, expiration: int = DEFAULT_EXPIRATION) -> None:
    """
    Store data in both local and Redis cache with expiration time.

    Args:
        key: Cache key
        data: Data to store
        expiration: Time in seconds until the cache expires (0 for no expiration)
    """
    # Store in local cache
    set_local_cache(key, data, expiration)

    # Store in Redis if available
    if REDIS_AVAILABLE:
        try:
            # Serialize the data to JSON
            serialized_data = json.dumps(data)
            if expiration > 0:
                redis_client.setex(key, expiration, serialized_data)
            else:
                redis_client.set(key, serialized_data)
            logger.debug(f"Stored in Redis cache: {key}, expires in {expiration}s")
        except Exception as e:
            logger.error(f"Redis error storing key {key}: {e}")


def set_local_cache(key: str, data: Any, expiration: int = DEFAULT_EXPIRATION) -> None:
    """
    Store data in local memory cache with expiration time.

    Args:
        key: Cache key
        data: Data to store
        expiration: Time in seconds until the cache expires (0 for no expiration)
    """
    with cache_lock:
        expiry_time = time.time() + expiration if expiration > 0 else 0
        LOCAL_CACHE[key] = {"data": data, "expiry": expiry_time}
    logger.debug(f"Stored in local cache: {key}, expires in {expiration}s")


def delete_cached_data(key: str) -> bool:
    """
    Delete an item from both caches.

    Args:
        key: Cache key to delete

    Returns:
        True if item was deleted from any cache, False if it didn't exist
    """
    local_deleted = False
    redis_deleted = False

    # Remove from local cache
    with cache_lock:
        if key in LOCAL_CACHE:
            del LOCAL_CACHE[key]
            local_deleted = True
            logger.debug(f"Deleted from local cache: {key}")

    # Remove from Redis if available
    if REDIS_AVAILABLE:
        try:
            redis_deleted = redis_client.delete(key) > 0
            if redis_deleted:
                logger.debug(f"Deleted from Redis cache: {key}")
        except Exception as e:
            logger.error(f"Redis error deleting key {key}: {e}")

    return local_deleted or redis_deleted


def clear_cache() -> None:
    """
    Clear all items from both caches.
    """
    # Clear local cache
    with cache_lock:
        LOCAL_CACHE.clear()
    logger.debug("Local cache cleared")

    # Clear Redis cache if available
    if REDIS_AVAILABLE:
        try:
            redis_client.flushdb()
            logger.debug("Redis cache cleared")
        except Exception as e:
            logger.error(f"Redis error clearing cache: {e}")


def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about both caches.

    Returns:
        Dictionary with cache statistics
    """
    stats = {
        "local_cache": {
            "total_entries": 0,
            "valid_entries": 0,
            "expired_entries": 0,
            "memory_usage_bytes": 0,
        },
        "redis_cache": {
            "available": REDIS_AVAILABLE,
            "total_entries": 0,
            "memory_usage_bytes": 0,
        },
    }

    # Local cache stats
    with cache_lock:
        total_entries = len(LOCAL_CACHE)
        expired_entries = sum(
            1
            for entry in LOCAL_CACHE.values()
            if entry["expiry"] > 0 and entry["expiry"] < time.time()
        )

        stats["local_cache"]["total_entries"] = total_entries
        stats["local_cache"]["expired_entries"] = expired_entries
        stats["local_cache"]["valid_entries"] = total_entries - expired_entries

        # Rough estimate of memory usage
        memory_usage = 0
        for key, entry in LOCAL_CACHE.items():
            try:
                memory_usage += len(json.dumps(entry["data"]))
            except:
                memory_usage += 100

        stats["local_cache"]["memory_usage_bytes"] = memory_usage

    # Redis stats if available
    if REDIS_AVAILABLE:
        try:
            stats["redis_cache"]["total_entries"] = redis_client.dbsize()
            # Get memory info if available (works on Redis >= 4.0)
            try:
                memory_info = redis_client.info("memory")
                stats["redis_cache"]["memory_usage_bytes"] = memory_info.get(
                    "used_memory", 0
                )
            except:
                pass
        except Exception as e:
            logger.error(f"Redis error getting cache stats: {e}")

    return stats


def cleanup_expired_entries() -> int:
    """
    Remove all expired entries from the local cache.
    Note: Redis handles its own expiration.

    Returns:
        Number of entries removed
    """
    count = 0
    current_time = time.time()

    with cache_lock:
        keys_to_delete = [
            key
            for key, entry in LOCAL_CACHE.items()
            if entry["expiry"] > 0 and entry["expiry"] < current_time
        ]

        for key in keys_to_delete:
            del LOCAL_CACHE[key]
            count += 1

    if count > 0:
        logger.debug(f"Cleaned up {count} expired local cache entries")

    return count


# For backward compatibility with existing code
class LLMCache:
    """Cache for LLM responses."""

    def __init__(self, cache_size=LLM_CACHE_SIZE):
        """Initialize the LLM cache.

        Args:
            cache_size: Maximum number of items in the cache
        """
        self.cache_size = cache_size

    def get_response(self, prompt: str, model: str = "default") -> Optional[str]:
        """Get a cached LLM response.

        Args:
            prompt: Prompt text
            model: Model name

        Returns:
            Cached response or None if not found
        """
        key = CacheKeyBuilder.llm_response_key(prompt, model)
        return get_cached_data(key)

    def add_response(self, prompt: str, response: str, model: str = "default") -> None:
        """Add an LLM response to the cache.

        Args:
            prompt: Prompt text
            response: LLM response
            model: Model name
        """
        key = CacheKeyBuilder.llm_response_key(prompt, model)
        set_cached_data(key, response, CACHE_TTL)


def get_memoized_value(key: str, factory, ttl: int = None) -> Any:
    """Get a value from the cache or generate it if not present.

    Args:
        key: Cache key
        factory: Function to generate the value if not cached
        ttl: Time to live in seconds

    Returns:
        The cached or generated value
    """
    value = get_cached_data(key)
    if value is None:
        value = factory()
        set_cached_data(key, value, ttl or CACHE_TTL)
    return value


def batch_get_values(keys: List[str]) -> Dict[str, Any]:
    """Get multiple values from the cache.

    Args:
        keys: List of cache keys

    Returns:
        Dictionary of key-value pairs for found keys
    """
    result = {}

    # First check local cache
    with cache_lock:
        for key in keys:
            if key in LOCAL_CACHE:
                entry = LOCAL_CACHE[key]
                if entry["expiry"] > time.time() or entry["expiry"] == 0:
                    result[key] = entry["data"]

    # Then check Redis for missing keys if available
    if REDIS_AVAILABLE and len(result) < len(keys):
        missing_keys = [key for key in keys if key not in result]
        try:
            if missing_keys:
                # Use mget for batch retrieval
                values = redis_client.mget(missing_keys)
                for key, value in zip(missing_keys, values):
                    if value is not None:
                        # Deserialize the data from JSON
                        deserialized = json.loads(value)
                        result[key] = deserialized
                        # Update local cache
                        set_local_cache(key, deserialized, redis_client.ttl(key))
        except Exception as e:
            logger.error(f"Redis error batch getting values: {e}")

    return result


def batch_get_or_set_values(
    keys_and_factories: Dict[str, callable], ttl: int = None
) -> Dict[str, Any]:
    """Get multiple values from the cache or generate them if not present.

    Args:
        keys_and_factories: Dictionary mapping keys to factory functions
        ttl: Time to live in seconds

    Returns:
        Dictionary of key-value pairs
    """
    ttl = ttl or CACHE_TTL
    values = batch_get_values(list(keys_and_factories.keys()))

    # Generate missing values
    missing_mapping = {}
    for key, factory in keys_and_factories.items():
        if key not in values:
            value = factory()
            values[key] = value
            missing_mapping[key] = value

    # Set missing values in cache
    if missing_mapping:
        for key, value in missing_mapping.items():
            set_cached_data(key, value, ttl)

    return values
