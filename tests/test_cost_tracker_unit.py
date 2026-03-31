"""Unit tests for cost tracker module."""

import asyncio
import pytest
from src.cost_tracker import CostTracker, UsageRecord, calculate_cost


class TestCalculateCost:
    """Tests for calculate_cost function (sync, no async needed)."""

    def test_sonnet_pricing(self):
        usage = UsageRecord(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = calculate_cost("claude-sonnet-4-6", usage)
        assert cost == pytest.approx(18.0)

    def test_opus_46_pricing(self):
        usage = UsageRecord(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = calculate_cost("claude-opus-4-6", usage)
        assert cost == pytest.approx(30.0)

    def test_haiku_pricing(self):
        usage = UsageRecord(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = calculate_cost("claude-haiku-4-5-20251001", usage)
        assert cost == pytest.approx(6.0)

    def test_cache_tokens(self):
        usage = UsageRecord(cache_read_tokens=1_000_000, cache_creation_tokens=1_000_000)
        cost = calculate_cost("claude-sonnet-4-6", usage)
        assert cost == pytest.approx(4.05)

    def test_web_search(self):
        usage = UsageRecord(web_search_requests=5)
        cost = calculate_cost("claude-sonnet-4-6", usage)
        assert cost == pytest.approx(0.05)

    def test_zero_usage(self):
        usage = UsageRecord()
        cost = calculate_cost("claude-sonnet-4-6", usage)
        assert cost == 0.0

    def test_unknown_model_uses_default(self):
        usage = UsageRecord(input_tokens=1_000_000, output_tokens=1_000_000)
        cost = calculate_cost("unknown-model-xyz", usage)
        assert cost == pytest.approx(18.0)

    def test_small_usage(self):
        usage = UsageRecord(input_tokens=100, output_tokens=50)
        cost = calculate_cost("claude-sonnet-4-6", usage)
        assert cost == pytest.approx(0.00105)


@pytest.mark.asyncio
class TestCostTracker:
    """Tests for CostTracker class (async methods)."""

    async def test_record_usage(self):
        tracker = CostTracker()
        usage = UsageRecord(input_tokens=1000, output_tokens=500)
        cost = await tracker.record_usage("session-1", "claude-sonnet-4-6", usage)
        assert cost > 0

    async def test_session_accumulation(self):
        tracker = CostTracker()
        usage = UsageRecord(input_tokens=1000, output_tokens=500)
        await tracker.record_usage("session-1", "claude-sonnet-4-6", usage)
        await tracker.record_usage("session-1", "claude-sonnet-4-6", usage)

        session = await tracker.get_session_cost("session-1")
        assert session is not None
        assert session.request_count == 2
        assert session.total_input_tokens == 2000
        assert session.total_output_tokens == 1000

    async def test_multiple_sessions(self):
        tracker = CostTracker()
        usage = UsageRecord(input_tokens=1000, output_tokens=500)
        await tracker.record_usage("session-1", "claude-sonnet-4-6", usage)
        await tracker.record_usage("session-2", "claude-opus-4-6", usage)

        summary = await tracker.get_all_sessions_summary()
        assert summary["active_sessions"] == 2
        assert summary["total_requests"] == 2

    async def test_per_model_tracking(self):
        tracker = CostTracker()
        await tracker.record_usage("s1", "claude-sonnet-4-6", UsageRecord(input_tokens=100))
        await tracker.record_usage("s1", "claude-opus-4-6", UsageRecord(input_tokens=200))

        summary = await tracker.get_session_summary("s1")
        assert "claude-sonnet-4-6" in summary["model_usage"]
        assert "claude-opus-4-6" in summary["model_usage"]
        assert summary["model_usage"]["claude-sonnet-4-6"]["requests"] == 1
        assert summary["model_usage"]["claude-opus-4-6"]["requests"] == 1

    async def test_delete_session(self):
        tracker = CostTracker()
        await tracker.record_usage("s1", "claude-sonnet-4-6", UsageRecord(input_tokens=100))
        assert await tracker.delete_session("s1") is True
        assert await tracker.get_session_cost("s1") is None
        assert await tracker.delete_session("s1") is False

    async def test_nonexistent_session_summary(self):
        tracker = CostTracker()
        summary = await tracker.get_session_summary("nonexistent")
        assert summary["total_cost_usd"] == 0.0
        assert summary["request_count"] == 0

    async def test_cleanup_expired(self):
        tracker = CostTracker(max_age_minutes=0)  # Expire immediately
        await tracker.record_usage("s1", "claude-sonnet-4-6", UsageRecord(input_tokens=100))
        removed = await tracker.cleanup_expired()
        assert removed == 1
        assert await tracker.get_session_cost("s1") is None

    async def test_cleanup_keeps_fresh_sessions(self):
        tracker = CostTracker(max_age_minutes=60)
        await tracker.record_usage("s1", "claude-sonnet-4-6", UsageRecord(input_tokens=100))
        removed = await tracker.cleanup_expired()
        assert removed == 0
        assert await tracker.get_session_cost("s1") is not None
