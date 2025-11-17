"""Simple time-based caching for expensive/slow-changing API calls."""

import time
from typing import Any, Optional, Callable
import logging


class TTLCache:
    """Time-to-live cache for API responses."""

    def __init__(self):
        """Initialize cache storage."""
        self._cache = {}

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if time.time() > entry["expires_at"]:
            # Expired
            del self._cache[key]
            return None

        logging.debug(f"Cache HIT: {key}")
        return entry["value"]

    def set(self, key: str, value: Any, ttl_seconds: int):
        """Set cache value with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
        """
        self._cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl_seconds,
        }
        logging.debug(f"Cache SET: {key} (TTL: {ttl_seconds}s)")

    def clear(self):
        """Clear all cached values."""
        self._cache.clear()
        logging.debug("Cache cleared")


# Global cache instance
_global_cache = TTLCache()


def cached(ttl_seconds: int):
    """Decorator for caching function results.

    Args:
        ttl_seconds: Time to live in seconds

    Example:
        @cached(ttl_seconds=3600)  # Cache for 1 hour
        def get_expensive_data():
            return fetch_from_api()
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            key_parts = [func.__name__]
            if args:
                key_parts.extend(str(arg) for arg in args)
            if kwargs:
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # Check cache
            cached_value = _global_cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = func(*args, **kwargs)
            if result is not None:  # Don't cache None/errors
                _global_cache.set(cache_key, result, ttl_seconds)

            return result

        return wrapper
    return decorator


def get_cache() -> TTLCache:
    """Get global cache instance.

    Returns:
        Global TTLCache instance
    """
    return _global_cache
