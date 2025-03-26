"""
Redis caching functionality for the CLI application.
"""

import json
from typing import Any, Dict, Optional, Union
import redis
from datetime import datetime, timedelta

from .config import REDIS_URL, CACHE_TTL, LLM_CACHE_SIZE


class Cache:
    """Redis cache implementation for the CLI application."""

    def __init__(self):
        """Initialize the Redis cache."""
        self.redis_client = redis.from_url(REDIS_URL)
        self._setup_cache()

    def _setup_cache(self) -> None:
        """Set up the Redis cache with initial configuration."""
        # Set up LLM cache size limit
        self.redis_client.config_set("maxmemory", f"{LLM_CACHE_SIZE}mb")
        self.redis_client.config_set("maxmemory-policy", "allkeys-lru")

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"Error getting value from cache: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (defaults to CACHE_TTL)
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if successful, False otherwise
        """
        try:
            value_json = json.dumps(value)
            return self.redis_client.set(
                key,
                value_json,
                ex=ttl or CACHE_TTL,
                nx=nx,
                xx=xx,
            )
        except Exception as e:
            print(f"Error setting value in cache: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            print(f"Error deleting key from cache: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            print(f"Error checking key existence in cache: {e}")
            return False

    def get_ttl(self, key: str) -> Optional[int]:
        """Get the time to live for a key.

        Args:
            key: Cache key

        Returns:
            Time to live in seconds or None if key doesn't exist
        """
        try:
            ttl = self.redis_client.ttl(key)
            return ttl if ttl > 0 else None
        except Exception as e:
            print(f"Error getting TTL for key: {e}")
            return None

    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set the time to live for a key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            return bool(self.redis_client.expire(key, ttl))
        except Exception as e:
            print(f"Error setting TTL for key: {e}")
            return False

    def clear(self) -> bool:
        """Clear all keys from the cache.

        Returns:
            True if successful, False otherwise
        """
        try:
            return bool(self.redis_client.flushdb())
        except Exception as e:
            print(f"Error clearing cache: {e}")
            return False

    def get_size(self) -> int:
        """Get the current size of the cache in bytes.

        Returns:
            Current size of the cache in bytes
        """
        try:
            info = self.redis_client.info(section="memory")
            return info.get("used_memory", 0)
        except Exception as e:
            print(f"Error getting cache size: {e}")
            return 0

    def get_keys(self, pattern: str = "*") -> list:
        """Get all keys matching a pattern.

        Args:
            pattern: Pattern to match keys against

        Returns:
            List of matching keys
        """
        try:
            return self.redis_client.keys(pattern)
        except Exception as e:
            print(f"Error getting keys from cache: {e}")
            return []

    def get_many(self, keys: list) -> Dict[str, Any]:
        """Get multiple values from the cache.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs
        """
        try:
            values = self.redis_client.mget(keys)
            return {
                key: json.loads(value)
                for key, value in zip(keys, values)
                if value is not None
            }
        except Exception as e:
            print(f"Error getting multiple values from cache: {e}")
            return {}

    def set_many(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set multiple values in the cache.

        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds (defaults to CACHE_TTL)

        Returns:
            True if successful, False otherwise
        """
        try:
            pipeline = self.redis_client.pipeline()
            for key, value in mapping.items():
                value_json = json.dumps(value)
                pipeline.set(key, value_json, ex=ttl or CACHE_TTL)
            return bool(pipeline.execute())
        except Exception as e:
            print(f"Error setting multiple values in cache: {e}")
            return False

    def delete_many(self, keys: list) -> bool:
        """Delete multiple keys from the cache.

        Args:
            keys: List of cache keys

        Returns:
            True if successful, False otherwise
        """
        try:
            return bool(self.redis_client.delete(*keys))
        except Exception as e:
            print(f"Error deleting multiple keys from cache: {e}")
            return False

    def get_or_set(
        self,
        key: str,
        default: Any,
        ttl: Optional[int] = None,
    ) -> Any:
        """Get a value from the cache or set a default if not found.

        Args:
            key: Cache key
            default: Default value to set if key not found
            ttl: Time to live in seconds (defaults to CACHE_TTL)

        Returns:
            Cached value or default value
        """
        value = self.get(key)
        if value is None:
            self.set(key, default, ttl)
            return default
        return value

    def get_or_set_many(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get multiple values from the cache or set defaults if not found.

        Args:
            mapping: Dictionary of key-default pairs
            ttl: Time to live in seconds (defaults to CACHE_TTL)

        Returns:
            Dictionary of key-value pairs
        """
        keys = list(mapping.keys())
        values = self.get_many(keys)
        missing_keys = set(keys) - set(values.keys())
        if missing_keys:
            missing_mapping = {key: mapping[key] for key in missing_keys}
            self.set_many(missing_mapping, ttl)
            values.update(missing_mapping)
        return values
