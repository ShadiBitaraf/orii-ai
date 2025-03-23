"""
Caching configuration for ORII.
Handles Redis caching and monitoring.
"""

import os
import json
import hashlib
import redis
from functools import lru_cache
from typing import Optional, Any, Callable
from .prometheus import record_cache_operation


class CacheManager:
    """Manager class for handling caching operations"""

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize the cache manager

        Args:
            redis_url: Optional Redis URL. If not provided, will use environment variable.
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self.connect()

    def connect(self):
        """Establish Redis connection"""
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.redis_client.ping()  # Test connection
        except redis.ConnectionError:
            print("Warning: Redis not available")
            self.redis_client = None

    def generate_key(self, prefix: str, content: str) -> str:
        """
        Generate a cache key

        Args:
            prefix: Key prefix for namespace
            content: Content to hash

        Returns:
            Cache key string
        """
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return f"{prefix}:{content_hash}"

    def get(self, key: str) -> Optional[str]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value if found, None otherwise
        """
        if not self.redis_client:
            record_cache_operation("redis", False)
            return None

        try:
            value = self.redis_client.get(key)
            hit = value is not None
            record_cache_operation("redis", hit)
            return value.decode("utf-8") if value else None
        except Exception as e:
            print(f"Cache get error: {str(e)}")
            record_cache_operation("redis", False)
            return None

    def set(self, key: str, value: str, ttl: int = 300) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.redis_client:
            return False

        try:
            return bool(self.redis_client.setex(key, ttl, value))
        except Exception as e:
            print(f"Cache set error: {str(e)}")
            return False


class LRUCache:
    """In-memory LRU cache wrapper with monitoring"""

    def __init__(self, maxsize: int = 100):
        """
        Initialize LRU cache

        Args:
            maxsize: Maximum size of the cache
        """
        self.maxsize = maxsize

    def decorator(self, func: Callable) -> Callable:
        """
        Decorator for caching function results

        Args:
            func: Function to cache

        Returns:
            Wrapped function
        """

        @lru_cache(maxsize=self.maxsize)
        def wrapped(*args, **kwargs):
            result = func(*args, **kwargs)
            record_cache_operation("memory", True)
            return result

        def wrapper(*args, **kwargs):
            # Check if result is in cache
            if wrapped.cache_info().hits > wrapped.cache_info().misses:
                record_cache_operation("memory", True)
            else:
                record_cache_operation("memory", False)
            return wrapped(*args, **kwargs)

        return wrapper


# Global cache instances
cache_manager = CacheManager()
lru_cache = LRUCache()
