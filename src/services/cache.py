"""Caching utilities for external service responses."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, ParamSpec

from core.logging_config import get_logger

LOGGER = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class CacheEntry:
    """A single cache entry with TTL support."""

    value: Any
    created_at: float
    ttl_seconds: float

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds


class TTLCache:
    """
    Simple in-memory cache with TTL (time-to-live) support.
    
    Thread-safe for reads but not for writes. For production use
    with high concurrency, consider using cachetools.TTLCache or Redis.
    """

    def __init__(self, default_ttl_seconds: float = 3600):
        """
        Initialize the cache.
        
        Args:
            default_ttl_seconds: Default TTL for entries (1 hour).
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Generate a cache key from arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key.
            
        Returns:
            Cached value or None if not found/expired.
        """
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """
        Set a value in the cache.
        
        Args:
            key: Cache key.
            value: Value to cache.
            ttl_seconds: TTL in seconds (uses default if not specified).
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._cache[key] = CacheEntry(
            value=value,
            created_at=time.time(),
            ttl_seconds=ttl,
        )

    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key.
            
        Returns:
            True if the key existed and was deleted.
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.
        
        Returns:
            Number of entries removed.
        """
        expired_keys = [
            key for key, entry in self._cache.items() if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    @property
    def size(self) -> int:
        """Get the number of entries in the cache."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Get the cache hit rate (0.0 - 1.0)."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 3),
        }


# Global cache instances for different services
_geocode_cache = TTLCache(default_ttl_seconds=168 * 3600)  # 1 week
_usps_cache = TTLCache(default_ttl_seconds=168 * 3600)  # 1 week
_comps_cache = TTLCache(default_ttl_seconds=24 * 3600)  # 24 hours


def get_geocode_cache() -> TTLCache:
    """Get the global geocode cache instance."""
    return _geocode_cache


def get_usps_cache() -> TTLCache:
    """Get the global USPS cache instance."""
    return _usps_cache


def get_comps_cache() -> TTLCache:
    """Get the global comps cache instance."""
    return _comps_cache


def cached(
    cache: TTLCache,
    ttl_seconds: Optional[float] = None,
    key_prefix: str = "",
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to cache function results.
    
    Args:
        cache: TTLCache instance to use.
        ttl_seconds: TTL for cached results (uses cache default if None).
        key_prefix: Prefix for cache keys.
        
    Returns:
        Decorated function with caching.
    
    Example:
        @cached(get_geocode_cache(), ttl_seconds=86400)
        def geocode(address: str) -> dict:
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Generate cache key
            key_data = json.dumps(
                {"prefix": key_prefix, "func": func.__name__, "args": args, "kwargs": kwargs},
                sort_keys=True,
                default=str,
            )
            cache_key = hashlib.sha256(key_data.encode()).hexdigest()

            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                LOGGER.debug(f"Cache hit for {func.__name__}")
                return cached_value

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl_seconds)
            LOGGER.debug(f"Cached result for {func.__name__}")
            return result

        return wrapper

    return decorator


__all__ = [
    "TTLCache",
    "CacheEntry",
    "get_geocode_cache",
    "get_usps_cache",
    "get_comps_cache",
    "cached",
]

