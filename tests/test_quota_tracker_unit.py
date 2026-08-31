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


class TestQuotaTrackerUnifiedWindows:
    """The SDK models only the representative window, but the CLI sends every
    window under raw["unifiedWindows"], and that is the only place utilization
    appears. Reading just the modelled fields lost seven_day entirely and
    reported a null utilization for everything."""

    @staticmethod
    def _real_payload():
        """Verbatim shape observed from the CLI on 2026-08-30."""
        return {
            "status": "allowed",
            "rate_limit_type": "five_hour",
            "resets_at": 1788145200,
            "overage_status": "rejected",
            "overage_disabled_reason": "org_level_disabled",
            "raw": {
                "unifiedWindows": {
                    "five_hour": {"utilization": 0.29, "resetsAt": 1788145200},
                    "seven_day": {"utilization": 0.05, "resetsAt": 1788732000},
                }
            },
        }

    def test_seven_day_is_recorded(self):
        tracker = QuotaTracker()
        tracker.record(self._real_payload())
        windows = tracker.snapshot()["windows"]
        assert "seven_day" in windows
        assert windows["seven_day"]["utilization"] == 0.05
        assert windows["seven_day"]["resets_at"] == 1788732000

    def test_utilization_comes_from_unified_windows(self):
        """The top-level payload carries no utilization field at all."""
        tracker = QuotaTracker()
        tracker.record(self._real_payload())
        assert tracker.snapshot()["windows"]["five_hour"]["utilization"] == 0.29

    def test_only_the_named_window_carries_a_status(self):
        tracker = QuotaTracker()
        tracker.record(self._real_payload())
        windows = tracker.snapshot()["windows"]
        assert windows["five_hour"]["status"] == "allowed"
        assert windows["five_hour"]["representative"] is True
        assert windows["seven_day"]["status"] is None
        assert windows["seven_day"]["representative"] is False

    def test_binding_window_is_named(self):
        tracker = QuotaTracker()
        tracker.record(self._real_payload())
        assert tracker.snapshot()["binding_window"] == "five_hour"

    def test_closest_to_limit_ignores_which_window_the_cli_named(self):
        """The weekly window can be nearest the cap while the CLI names the
        five-hour one; the summary must report the real constraint."""
        payload = self._real_payload()
        payload["raw"]["unifiedWindows"]["seven_day"]["utilization"] = 0.97
        tracker = QuotaTracker()
        tracker.record(payload)
        closest = tracker.snapshot()["closest_to_limit"]
        assert closest["window"] == "seven_day"
        assert closest["utilization"] == 0.97

    def test_overage_disabled_reason_is_surfaced(self):
        """A rejected overage pool reads as alarming until you see why."""
        tracker = QuotaTracker()
        tracker.record(self._real_payload())
        overage = tracker.snapshot()["windows"]["overage"]
        assert overage["status"] == "rejected"
        assert overage["disabled_reason"] == "org_level_disabled"

    def test_rejected_overage_alone_does_not_block(self):
        tracker = QuotaTracker()
        tracker.record(self._real_payload())
        assert tracker.snapshot()["blocked"] is False

    def test_falls_back_when_unified_windows_absent(self):
        """Older CLI builds send no unifiedWindows key."""
        tracker = QuotaTracker()
        tracker.record(_info(utilization=0.42))
        window = tracker.snapshot()["windows"]["five_hour"]
        assert window["utilization"] == 0.42
        assert window["representative"] is True


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


class TestQuotaErrorText:
    def test_session_limit_wording_matches(self):
        from src.quota_tracker import is_quota_error_text

        assert is_quota_error_text(
            "Claude Code returned an error result: You've hit your session limit"
        )

    def test_usage_limit_and_quota_match(self):
        from src.quota_tracker import is_quota_error_text

        assert is_quota_error_text("usage limit reached|resets_at")
        assert is_quota_error_text("upstream quota exhausted")

    def test_unrelated_text_does_not_match(self):
        from src.quota_tracker import is_quota_error_text

        assert not is_quota_error_text("connection reset by peer")
        assert not is_quota_error_text("")
        assert not is_quota_error_text(None)


class TestParseResetClockTime:
    # 2026-08-31 17:22:16 UTC, the timestamp of the observed stall.
    NOW = 1788196936.0

    def test_pm_hour_later_today(self):
        from src.quota_tracker import parse_reset_clock_time

        resets = parse_reset_clock_time(
            "You've hit your session limit · resets 6pm (UTC)", now=self.NOW
        )
        # 18:00 UTC the same day.
        assert resets is not None
        assert resets - self.NOW == pytest.approx(2264, abs=1)

    def test_hour_already_passed_rolls_to_tomorrow(self):
        from src.quota_tracker import parse_reset_clock_time

        resets = parse_reset_clock_time("resets 3am (UTC)", now=self.NOW)
        assert resets is not None
        assert resets > self.NOW
        assert (resets - self.NOW) < 24 * 3600

    def test_minutes_and_at_are_accepted(self):
        from src.quota_tracker import parse_reset_clock_time

        resets = parse_reset_clock_time("resets at 11:30pm (UTC)", now=self.NOW)
        assert resets is not None
        assert (resets - self.NOW) == pytest.approx(22064, abs=1)

    def test_twelve_pm_is_noon_and_twelve_am_is_midnight(self):
        from src.quota_tracker import parse_reset_clock_time

        noon = parse_reset_clock_time("resets 12pm (UTC)", now=self.NOW)
        midnight = parse_reset_clock_time("resets 12am (UTC)", now=self.NOW)
        assert noon is not None and midnight is not None
        # Both already passed or land tomorrow relative to 13:22 UTC.
        assert (noon - self.NOW) < 24 * 3600
        assert (midnight - self.NOW) < 24 * 3600

    def test_no_reset_phrase_returns_none(self):
        from src.quota_tracker import parse_reset_clock_time

        assert parse_reset_clock_time("You've hit your session limit") is None
        assert parse_reset_clock_time("resets soon") is None
        assert parse_reset_clock_time("") is None
