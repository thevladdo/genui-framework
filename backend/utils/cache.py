"""
Caching utilities for LLM responses and RAG results.
"""

import hashlib
import json
import logging
from typing import Any, Callable, Optional
from functools import wraps
import os

logger = logging.getLogger(__name__)


class SimpleMemoryCache:
    """Simple in-memory cache with LRU-like behavior."""
    
    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, Any] = {}
        self._max_size = max_size
        self._access_order: list[str] = []
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._cache:
            # Move to end (most recently used)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with LRU eviction."""
        if key not in self._cache and len(self._cache) >= self._max_size:
            # Evict least recently used
            oldest = self._access_order.pop(0)
            del self._cache[oldest]
        
        self._cache[key] = value
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
    
    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        self._access_order.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


# Global cache instance
_global_cache = SimpleMemoryCache(max_size=1000)


def _generate_cache_key(*args, **kwargs) -> str:
    """Generate a stable cache key from function arguments."""
    # Create a stable representation of args and kwargs
    key_data = {
        "args": [str(arg) for arg in args],
        "kwargs": {k: str(v) for k, v in sorted(kwargs.items())}
    }
    key_str = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_str.encode()).hexdigest()


def cacheable(
    key_func: Optional[Callable] = None,
    ttl: Optional[int] = None,
    enabled: bool = True
):
    """
    Decorator for caching function results.
    
    Use this on expensive operations like LLM calls and RAG searches.
    
    Args:
        key_func: Optional function to generate cache key from args
        ttl: Time-to-live in seconds (not implemented in memory cache)
        enabled: Whether caching is enabled (can be controlled by env var)
    
    Example:
        @cacheable()
        async def expensive_llm_call(prompt: str) -> str:
            return await client.a_invoke(prompt)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Check if caching is disabled via environment
            cache_enabled = enabled and os.getenv("DISABLE_CACHE", "false").lower() != "true"
            
            if not cache_enabled:
                return await func(*args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__module__}.{func.__name__}:{_generate_cache_key(*args, **kwargs)}"
            
            # Check cache
            cached_value = _global_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_value
            
            # Call function and cache result
            logger.debug(f"Cache miss for {func.__name__}")
            result = await func(*args, **kwargs)
            _global_cache.set(cache_key, result)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Check if caching is disabled via environment
            cache_enabled = enabled and os.getenv("DISABLE_CACHE", "false").lower() != "true"
            
            if not cache_enabled:
                return func(*args, **kwargs)
            
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__module__}.{func.__name__}:{_generate_cache_key(*args, **kwargs)}"
            
            # Check cache
            cached_value = _global_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_value
            
            # Call function and cache result
            logger.debug(f"Cache miss for {func.__name__}")
            result = func(*args, **kwargs)
            _global_cache.set(cache_key, result)
            
            return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def clear_cache():
    """Clear the global cache."""
    _global_cache.clear()
    logger.info("Cache cleared")


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return {
        "size": _global_cache.size(),
        "max_size": _global_cache._max_size,
    }
