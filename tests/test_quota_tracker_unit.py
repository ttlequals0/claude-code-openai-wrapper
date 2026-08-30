"""Unit tests for src.quota_tracker.

Covers passive recording from SDK rate-limit events, per-window
independence, overage handling, blocking, the snapshot served by /v1/usage,
probe cadence, and env configuration.
"""

import time

import pytest

from src.quota_tracker import (
    QuotaTracker,
    probe_every_n_requests,
    probe_min_interval_seconds,
    quota_enforcement_enabled,
)


def _info(**overrides):
    """A RateLimitInfo-shaped dict; record() accepts dataclass or dict."""
    payload = {
        "status": "allowed",
        "resets_at": int(time.time()) + 3600,
        "rate_limit_type": "five_hour",
        "utilization": 0.5,
    }
    payload.update(overrides)
    return payload


class TestQuotaTrackerRecord:
    def test_records_the_sdk_dataclass(self):
        from claude_agent_sdk import RateLimitInfo

        tracker = QuotaTracker()
        tracker.record(
            RateLimitInfo(
                status="allowed_warning",
                resets_at=int(time.time()) + 60,
                rate_limit_type="seven_day",
                utilization=0.99,
            )
        )
        window = tracker.snapshot()["windows"]["seven_day"]
        assert window["status"] == "allowed_warning"
        assert window["utilization"] == 0.99

    def test_records_an_equivalent_dict(self):
        tracker = QuotaTracker()
        tracker.record(_info())
        assert tracker.snapshot()["windows"]["five_hour"]["status"] == "allowed"

    def test_ignores_payload_without_a_status(self):
        tracker = QuotaTracker()
        tracker.record({"rate_limit_type": "five_hour"})
        assert tracker.snapshot()["observed_windows"] == 0

    def test_windows_are_tracked_independently(self):
        """A five_hour report must not clear a known seven_day reading."""
        tracker = QuotaTracker()
        tracker.record(_info(rate_limit_type="seven_day", utilization=0.8))
        tracker.record(_info(rate_limit_type="five_hour", utilization=0.1))
        windows = tracker.snapshot()["windows"]
        assert windows["seven_day"]["utilization"] == 0.8
        assert windows["five_hour"]["utilization"] == 0.1

    def test_overage_is_stored_as_its_own_window(self):
        tracker = QuotaTracker()
        tracker.record(_info(overage_status="allowed", overage_resets_at=123))
        assert tracker.snapshot()["windows"]["overage"]["status"] == "allowed"

    def test_source_is_recorded(self):
        tracker = QuotaTracker()
        tracker.record(_info(), source="probe")
        assert tracker.snapshot()["windows"]["five_hour"]["source"] == "probe"


class TestQuotaTrackerBlocking:
    def test_not_blocked_when_allowed(self):
        tracker = QuotaTracker()
        tracker.record(_info(status="allowed"))
        assert tracker.blocked_until() is None

    def test_warning_status_does_not_block(self):
        tracker = QuotaTracker()
        tracker.record(_info(status="allowed_warning", utilization=0.97))
        assert tracker.blocked_until() is None

    def test_rejected_blocks_until_reset(self):
        reset = int(time.time()) + 1800
        tracker = QuotaTracker()
        tracker.record(_info(status="rejected", resets_at=reset))
        assert tracker.blocked_until() == reset

    def test_expired_rejection_no_longer_blocks(self):
        tracker = QuotaTracker()
        tracker.record(_info(status="rejected", resets_at=int(time.time()) - 10))
        assert tracker.blocked_until() is None

    def test_rejection_without_reset_blocks_with_unknown_time(self):
        """Zero, not None: blocked, but the caller cannot be told when."""
        tracker = QuotaTracker()
        tracker.record(_info(status="rejected", resets_at=None))
        assert tracker.blocked_until() == 0
        snapshot = tracker.snapshot()
        assert snapshot["blocked"] is True
        assert snapshot["blocked_until"] is None

    def test_available_overage_suppresses_blocking(self):
        tracker = QuotaTracker()
        tracker.record(
            _info(
                status="rejected",
                resets_at=int(time.time()) + 600,
                overage_status="allowed",
            )
        )
        assert tracker.blocked_until() is None

    def test_rejected_overage_does_not_suppress_blocking(self):
        reset = int(time.time()) + 600
        tracker = QuotaTracker()
        tracker.record(_info(status="rejected", resets_at=reset, overage_status="rejected"))
        assert tracker.blocked_until() == reset

    def test_stale_overage_does_not_suppress_a_newer_rejection(self):
        reset = int(time.time()) + 600
        tracker = QuotaTracker()
        tracker.record(_info(status="allowed", overage_status="allowed"))
        time.sleep(0.01)
        tracker.record(_info(status="rejected", resets_at=reset))
        assert tracker.blocked_until() == reset

    def test_latest_reset_wins_across_windows(self):
        near = int(time.time()) + 600
        far = int(time.time()) + 6000
        tracker = QuotaTracker()
        tracker.record(_info(status="rejected", rate_limit_type="five_hour", resets_at=near))
        tracker.record(_info(status="rejected", rate_limit_type="seven_day", resets_at=far))
        assert tracker.blocked_until() == far


class TestQuotaTrackerSnapshot:
    def test_empty_tracker_reports_no_windows(self):
        snapshot = QuotaTracker().snapshot()
        assert snapshot["blocked"] is False
        assert snapshot["observed_windows"] == 0
        assert snapshot["windows"] == {}

    def test_snapshot_exposes_unix_and_iso_reset(self):
        reset = int(time.time()) + 120
        tracker = QuotaTracker()
        tracker.record(_info(resets_at=reset))
        window = tracker.snapshot()["windows"]["five_hour"]
        assert window["resets_at"] == reset
        assert window["resets_at_iso"].endswith("+00:00")
        assert 0 < window["seconds_until_reset"] <= 120

    def test_fresh_reading_is_not_stale(self):
        tracker = QuotaTracker(stale_after_seconds=900)
        tracker.record(_info())
        assert tracker.snapshot()["windows"]["five_hour"]["stale"] is False

    def test_reading_goes_stale_after_the_threshold(self):
        tracker = QuotaTracker(stale_after_seconds=0)
        tracker.record(_info())
        time.sleep(0.01)
        assert tracker.snapshot()["windows"]["five_hour"]["stale"] is True


class TestQuotaTrackerProbeCadence:
    def test_probe_not_due_before_the_threshold(self):
        tracker = QuotaTracker()
        for _ in range(9):
            tracker.note_request()
        assert tracker.probe_due(10) is False

    def test_probe_due_at_the_threshold_and_resets(self):
        tracker = QuotaTracker()
        for _ in range(10):
            tracker.note_request()
        assert tracker.probe_due(10) is True
        assert tracker.probe_due(10) is False

    def test_zero_disables_probing(self):
        tracker = QuotaTracker()
        for _ in range(100):
            tracker.note_request()
        assert tracker.probe_due(0) is False


class TestQuotaTrackerConfigFromEnv:
    def test_defaults_when_unset(self, monkeypatch):
        for name in (
            "WRAPPER_QUOTA_ENFORCEMENT_ENABLED",
            "WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS",
            "WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS",
        ):
            monkeypatch.delenv(name, raising=False)
        assert quota_enforcement_enabled() is False
        assert probe_every_n_requests() == 100
        assert probe_min_interval_seconds() == 300

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", "true")
        monkeypatch.setenv("WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS", "25")
        monkeypatch.setenv("WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS", "60")
        assert quota_enforcement_enabled() is True
        assert probe_every_n_requests() == 25
        assert probe_min_interval_seconds() == 60

    def test_invalid_values_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv("WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS", "many")
        monkeypatch.setenv("WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS", "")
        assert probe_every_n_requests() == 100
        assert probe_min_interval_seconds() == 300

    @pytest.mark.parametrize("raw", ["1", "yes", "on", "TRUE"])
    def test_truthy_spellings_enable_enforcement(self, monkeypatch, raw):
        monkeypatch.setenv("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", raw)
        assert quota_enforcement_enabled() is True
