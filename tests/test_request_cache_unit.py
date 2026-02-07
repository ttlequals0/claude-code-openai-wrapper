#!/usr/bin/env python3
"""
Unit tests for request cache functionality.

Tests the RequestCache class including caching, TTL, LRU eviction,
and statistics tracking.
"""

import pytest
import time
from unittest.mock import patch

from src.request_cache import RequestCache, CacheEntry


class TestRequestCache:
    """Test RequestCache class."""

    def test_cache_set_and_get(self):
        """Basic set and get operations work."""
        cache = RequestCache(enabled=True, max_size=10, ttl_seconds=60)
        request = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}
        response = {"id": "123", "choices": [{"content": "Hi"}]}

        cache.set(request, response)
        result = cache.get(request)

        assert result == response

    def test_cache_miss(self):
        """Returns None for cache miss."""
        cache = RequestCache(enabled=True, max_size=10, ttl_seconds=60)
        request = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}

        result = cache.get(request)

        assert result is None

    def test_cache_disabled(self):
        """Returns None when cache is disabled."""
        cache = RequestCache(enabled=False, max_size=10, ttl_seconds=60)
        request = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}
        response = {"id": "123", "choices": [{"content": "Hi"}]}

        cache.set(request, response)
        result = cache.get(request)

        assert result is None

    def test_cache_expiration(self):
        """Entries expire after TTL."""
        cache = RequestCache(enabled=True, max_size=10, ttl_seconds=1)
        request = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}
        response = {"id": "123", "choices": [{"content": "Hi"}]}

        cache.set(request, response)

        # Should be present immediately
        assert cache.get(request) == response

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        assert cache.get(request) is None

    def test_lru_eviction(self):
        """LRU eviction when max_size is reached."""
        cache = RequestCache(enabled=True, max_size=2, ttl_seconds=60)

        request1 = {"model": "test", "messages": [{"role": "user", "content": "One"}]}
        request2 = {"model": "test", "messages": [{"role": "user", "content": "Two"}]}
        request3 = {"model": "test", "messages": [{"role": "user", "content": "Three"}]}

        cache.set(request1, {"id": "1"})
        cache.set(request2, {"id": "2"})

        # Access request1 to make it more recently used
        cache.get(request1)

        # Add request3, should evict request2 (least recently used)
        cache.set(request3, {"id": "3"})

        # request1 should still be present (was accessed)
        assert cache.get(request1) is not None
        # request3 should be present (just added)
        assert cache.get(request3) is not None
        # request2 should be evicted
        assert cache.get(request2) is None

    def test_stats_tracking(self):
        """Statistics are tracked correctly."""
        cache = RequestCache(enabled=True, max_size=10, ttl_seconds=60)
        request = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}
        response = {"id": "123", "choices": [{"content": "Hi"}]}

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Miss
        cache.get(request)
        stats = cache.get_stats()
        assert stats["misses"] == 1

        # Set and hit
        cache.set(request, response)
        cache.get(request)
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 50.0

    def test_clear(self):
        """Clear removes all entries."""
        cache = RequestCache(enabled=True, max_size=10, ttl_seconds=60)

        for i in range(5):
            request = {"model": "test", "messages": [{"role": "user", "content": f"Msg {i}"}]}
            cache.set(request, {"id": str(i)})

        stats = cache.get_stats()
        assert stats["current_size"] == 5

        cleared = cache.clear()

        assert cleared == 5
        stats = cache.get_stats()
        assert stats["current_size"] == 0

    def test_hash_deterministic(self):
        """Same request produces same hash."""
        cache = RequestCache(enabled=True)

        request1 = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}
        request2 = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}

        hash1 = cache._compute_hash(request1)
        hash2 = cache._compute_hash(request2)

        assert hash1 == hash2

    def test_hash_ignores_irrelevant_fields(self):
        """Hash ignores fields that don't affect response."""
        cache = RequestCache(enabled=True)

        request1 = {
            "model": "test",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
            "session_id": "abc123",
        }
        request2 = {
            "model": "test",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,  # Different
            "session_id": "xyz789",  # Different
        }

        hash1 = cache._compute_hash(request1)
        hash2 = cache._compute_hash(request2)

        assert hash1 == hash2

    def test_hash_differs_for_different_content(self):
        """Different content produces different hashes."""
        cache = RequestCache(enabled=True)

        request1 = {"model": "test", "messages": [{"role": "user", "content": "Hello"}]}
        request2 = {"model": "test", "messages": [{"role": "user", "content": "Goodbye"}]}

        hash1 = cache._compute_hash(request1)
        hash2 = cache._compute_hash(request2)

        assert hash1 != hash2

    def test_cleanup_expired(self):
        """cleanup_expired removes expired entries."""
        cache = RequestCache(enabled=True, max_size=10, ttl_seconds=1)

        request1 = {"model": "test", "messages": [{"role": "user", "content": "One"}]}
        request2 = {"model": "test", "messages": [{"role": "user", "content": "Two"}]}

        cache.set(request1, {"id": "1"})
        cache.set(request2, {"id": "2"})

        # Wait for expiration
        time.sleep(1.1)

        removed = cache.cleanup_expired()

        assert removed == 2
        assert cache.get_stats()["current_size"] == 0

    def test_stats_include_config(self):
        """Stats include configuration values."""
        cache = RequestCache(enabled=True, max_size=50, ttl_seconds=120)
        stats = cache.get_stats()

        assert stats["enabled"] is True
        assert stats["max_size"] == 50
        assert stats["ttl_seconds"] == 120

    def test_enabled_property(self):
        """enabled property reflects configuration."""
        cache_enabled = RequestCache(enabled=True)
        cache_disabled = RequestCache(enabled=False)

        assert cache_enabled.enabled is True
        assert cache_disabled.enabled is False


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """CacheEntry can be created with required fields."""
        entry = CacheEntry(
            response={"id": "test"},
            created_at=1000.0,
            expires_at=1060.0,
        )

        assert entry.response == {"id": "test"}
        assert entry.created_at == 1000.0
        assert entry.expires_at == 1060.0
        assert entry.hit_count == 0  # Default

    def test_cache_entry_hit_count(self):
        """CacheEntry hit_count can be specified."""
        entry = CacheEntry(
            response={"id": "test"},
            created_at=1000.0,
            expires_at=1060.0,
            hit_count=5,
        )

        assert entry.hit_count == 5
