"""
Request deduplication cache for Claude Code OpenAI Wrapper.

Provides an optional caching layer for identical requests to reduce API calls
and improve response times for repeated queries.
"""

import hashlib
import json
import os
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from collections import OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached response with metadata."""
    response: Dict[str, Any]
    created_at: float
    expires_at: float
    hit_count: int = 0


class RequestCache:
    """
    Thread-safe LRU cache with TTL for request deduplication.

    Features:
    - LRU eviction when max_size is reached
    - TTL-based expiration
    - Thread-safe operations
    - Deterministic request hashing
    """

    def __init__(
        self,
        enabled: bool = True,
        max_size: int = 100,
        ttl_seconds: int = 60,
    ):
        """
        Initialize the request cache.

        Args:
            enabled: Whether caching is enabled
            max_size: Maximum number of entries to store
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self._enabled = enabled
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }

    @property
    def enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled

    def _compute_hash(self, request_data: Dict[str, Any]) -> str:
        """
        Compute a deterministic hash for a request.

        Only includes fields that affect the response:
        - model
        - messages
        - temperature
        - max_tokens
        - response_format

        Excludes:
        - stream (caching only applies to non-streaming)
        - session_id
        - other metadata

        Args:
            request_data: The request dictionary

        Returns:
            A hex string hash of the request
        """
        # Extract only the fields that affect the response
        hashable_fields = {
            "model": request_data.get("model"),
            "messages": request_data.get("messages"),
            "temperature": request_data.get("temperature"),
            "max_tokens": request_data.get("max_tokens"),
            "response_format": request_data.get("response_format"),
            "top_p": request_data.get("top_p"),
        }

        # Convert to a stable JSON string (sorted keys)
        json_str = json.dumps(hashable_fields, sort_keys=True, default=str)

        # Compute SHA-256 hash
        return hashlib.sha256(json_str.encode()).hexdigest()

    def get(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get a cached response for a request.

        Args:
            request_data: The request dictionary

        Returns:
            Cached response if found and not expired, None otherwise
        """
        if not self._enabled:
            return None

        cache_key = self._compute_hash(request_data)
        current_time = time.time()

        with self._lock:
            if cache_key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[cache_key]

            # Check if expired
            if current_time > entry.expires_at:
                del self._cache[cache_key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                logger.debug(f"Cache entry expired for key {cache_key[:16]}...")
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            entry.hit_count += 1
            self._stats["hits"] += 1

            logger.debug(f"Cache hit for key {cache_key[:16]}... (hit_count={entry.hit_count})")
            return entry.response

    def set(self, request_data: Dict[str, Any], response: Dict[str, Any]) -> None:
        """
        Cache a response for a request.

        Args:
            request_data: The request dictionary
            response: The response to cache
        """
        if not self._enabled:
            return

        cache_key = self._compute_hash(request_data)
        current_time = time.time()

        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats["evictions"] += 1
                logger.debug(f"Evicted oldest cache entry {oldest_key[:16]}...")

            # Add new entry
            self._cache[cache_key] = CacheEntry(
                response=response,
                created_at=current_time,
                expires_at=current_time + self._ttl_seconds,
            )

            logger.debug(f"Cached response for key {cache_key[:16]}... (ttl={self._ttl_seconds}s)")

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared {count} cache entries")
            return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0

            return {
                "enabled": self._enabled,
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds,
                "current_size": len(self._cache),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate_percent": round(hit_rate, 2),
                "evictions": self._stats["evictions"],
                "expirations": self._stats["expirations"],
            }

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        removed = 0

        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time > entry.expires_at
            ]

            for key in expired_keys:
                del self._cache[key]
                removed += 1
                self._stats["expirations"] += 1

        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired cache entries")

        return removed


# Global cache instance with configuration from environment
request_cache = RequestCache(
    enabled=os.getenv("REQUEST_CACHE_ENABLED", "false").lower() in ("true", "1", "yes", "on"),
    max_size=int(os.getenv("REQUEST_CACHE_MAX_SIZE", "100")),
    ttl_seconds=int(os.getenv("REQUEST_CACHE_TTL_SECONDS", "60")),
)
