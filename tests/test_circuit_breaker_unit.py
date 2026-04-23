"""Unit tests for src.circuit_breaker.

Covers the state machine (closed -> open -> half-open -> closed/open),
threshold behavior, and half-open single-probe semantics.
"""

import time

from src.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


def _make_breaker(**overrides) -> CircuitBreaker:
    defaults = dict(
        window_seconds=10.0,
        failure_ratio_threshold=0.5,
        min_requests_for_trip=4,
        open_seconds=0.05,  # short cool-off for tests
    )
    defaults.update(overrides)
    return CircuitBreaker(CircuitBreakerConfig(**defaults))


class TestCircuitBreakerClosed:
    def test_starts_closed_and_allows_requests(self):
        b = _make_breaker()
        assert b.allow_request() is True
        assert b.state == CircuitBreakerState.CLOSED

    def test_success_keeps_breaker_closed(self):
        b = _make_breaker()
        for _ in range(20):
            assert b.allow_request()
            b.record(success=True)
        assert b.state == CircuitBreakerState.CLOSED

    def test_below_min_requests_does_not_trip(self):
        b = _make_breaker(min_requests_for_trip=10)
        for _ in range(3):
            b.allow_request()
            b.record(success=False)
        # Failure ratio 100% but min_requests not met.
        assert b.state == CircuitBreakerState.CLOSED


class TestCircuitBreakerOpens:
    def test_trips_when_failure_ratio_threshold_reached(self):
        b = _make_breaker()
        # 4 requests, all failures -> ratio 1.0 > 0.5, n=4 meets min_requests_for_trip.
        for _ in range(4):
            b.allow_request()
            b.record(success=False)
        assert b.state == CircuitBreakerState.OPEN

    def test_open_breaker_denies_new_requests(self):
        b = _make_breaker()
        for _ in range(4):
            b.allow_request()
            b.record(success=False)
        assert b.state == CircuitBreakerState.OPEN
        # Subsequent requests should be shed until cool-off elapses.
        assert b.allow_request() is False


class TestCircuitBreakerHalfOpen:
    def test_half_opens_after_cool_off_and_allows_one_probe(self):
        b = _make_breaker(open_seconds=0.01)
        for _ in range(4):
            b.allow_request()
            b.record(success=False)
        assert b.state == CircuitBreakerState.OPEN

        # Wait for cool-off, then a single probe is allowed.
        time.sleep(0.02)
        assert b.allow_request() is True
        assert b.state == CircuitBreakerState.HALF_OPEN
        # While probe is in flight, no additional requests.
        assert b.allow_request() is False

    def test_successful_probe_closes_breaker(self):
        b = _make_breaker(open_seconds=0.01)
        for _ in range(4):
            b.allow_request()
            b.record(success=False)
        time.sleep(0.02)
        assert b.allow_request() is True  # probe
        b.record(success=True)
        assert b.state == CircuitBreakerState.CLOSED
        assert b.allow_request() is True

    def test_failed_probe_reopens_breaker(self):
        b = _make_breaker(open_seconds=0.01)
        for _ in range(4):
            b.allow_request()
            b.record(success=False)
        time.sleep(0.02)
        assert b.allow_request() is True  # probe
        b.record(success=False)
        assert b.state == CircuitBreakerState.OPEN


class TestCircuitBreakerSnapshot:
    def test_snapshot_exposes_state_and_ratio(self):
        b = _make_breaker()
        b.allow_request(); b.record(success=True)
        b.allow_request(); b.record(success=False)
        snap = b.snapshot()
        assert snap["state"] == CircuitBreakerState.CLOSED
        assert snap["window_size"] == 2
        assert snap["failure_ratio"] == 0.5
