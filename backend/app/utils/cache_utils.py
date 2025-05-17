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
import hashlib

# Setup logger
logger = logging.getLogger(__name__)

# Import config directly to avoid circular imports
import os
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Cache configuration
CACHE_TTL = 300  # 5 minutes for development, adjust as needed
LLM_CACHE_SIZE = 100  # Number of LLM responses to cache in memory

# Development mode configuration
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
if DEV_MODE:
    # Reduce API calls in development
    CACHE_TTL = 3600  # 1 hour cache in dev mode

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
    Delete data from both local and Redis cache.

    Args:
        key: Cache key to delete

    Returns:
        True if deletion was successful, False otherwise
    """
    success = True

    # Delete from local cache
    with cache_lock:
        if key in LOCAL_CACHE:
            del LOCAL_CACHE[key]
            logger.debug(f"Deleted from local cache: {key}")
        else:
            success = False

    # Delete from Redis if available
    if REDIS_AVAILABLE:
        try:
            result = redis_client.delete(key)
            if result:
                logger.debug(f"Deleted from Redis cache: {key}")
            else:
                success = False
        except Exception as e:
            logger.error(f"Redis error deleting key {key}: {e}")
            success = False

    return success


def clear_cache() -> None:
    """
    Clear all cache data from both local memory and Redis.
    """
    # Clear local cache
    with cache_lock:
        LOCAL_CACHE.clear()
        logger.info("Local cache cleared")

    # Clear Redis cache if available
    if REDIS_AVAILABLE:
        try:
            redis_client.flushdb()
            logger.info("Redis cache cleared")
        except Exception as e:
            logger.error(f"Error clearing Redis cache: {e}")


def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the cache.

    Returns:
        Dictionary with cache statistics
    """
    stats = {
        "local_cache_keys": 0,
        "local_cache_size_bytes": 0,
        "redis_keys": 0,
        "redis_size_bytes": 0,
        "keys": 0,
        "size_bytes": 0,
    }

    # Get local cache stats
    with cache_lock:
        stats["local_cache_keys"] = len(LOCAL_CACHE)
        # Estimate size of local cache in bytes
        try:
            import sys
            import gzip
            from io import BytesIO

            # Serialize the cache and compress it to estimate size
            serialized = json.dumps(
                {key: value["data"] for key, value in LOCAL_CACHE.items()}
            ).encode()
            compressed = BytesIO()
            with gzip.GzipFile(fileobj=compressed, mode="wb") as f:
                f.write(serialized)
            stats["local_cache_size_bytes"] = sys.getsizeof(compressed.getvalue())
        except Exception as e:
            logger.error(f"Error calculating local cache size: {e}")
            stats["local_cache_size_bytes"] = 0

    # Get Redis stats if available
    if REDIS_AVAILABLE:
        try:
            stats["redis_keys"] = redis_client.dbsize()
            # Get Redis memory usage if available
            try:
                info = redis_client.info("memory")
                stats["redis_size_bytes"] = info.get("used_memory", 0)
            except:
                stats["redis_size_bytes"] = 0
        except Exception as e:
            logger.error(f"Error getting Redis stats: {e}")
            stats["redis_keys"] = 0
            stats["redis_size_bytes"] = 0

    # Calculate totals
    stats["keys"] = stats["local_cache_keys"] + stats["redis_keys"]
    stats["size_bytes"] = stats["local_cache_size_bytes"] + stats["redis_size_bytes"]

    return stats
