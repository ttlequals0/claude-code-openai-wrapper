"""Simple in-process circuit breaker for upstream-SDK failures.

When the Claude Agent SDK returns a high rate of errors over a short window,
continuing to forward requests just amplifies load on an already-bad upstream
and delays each caller by the full wall-clock of a doomed attempt. This
breaker cuts that loop: once the recent failure rate crosses a threshold,
new requests fail-fast with 503 for a short cool-off period, then half-open
by allowing a single probe request through. A success closes the breaker;
another failure re-opens it.

The breaker is intentionally small and has no external dependencies. It is
suitable for a single wrapper process; multi-replica deployments should
either accept independent breaker state or place a shared breaker
(e.g. via Redis) in front.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple


@dataclass(frozen=True)
class CircuitBreakerConfig:
    window_seconds: float = 60.0
    failure_ratio_threshold: float = 0.5
    min_requests_for_trip: int = 10
    open_seconds: float = 30.0


class CircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Rolling-window failure-rate breaker.

    Thread-safe. Every request records an outcome with ``record()``, and
    ``allow_request()`` returns False when the breaker is open and no cool-off
    probe window has elapsed yet. On half-open, a single probe is allowed
    through; its outcome either closes or re-opens the breaker.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._cfg = config or CircuitBreakerConfig()
        self._history: Deque[Tuple[float, bool]] = deque()
        self._lock = threading.Lock()
        self._state = CircuitBreakerState.CLOSED
        self._opened_at: float | None = None
        self._probe_in_flight = False

    def _prune(self, now: float) -> None:
        cutoff = now - self._cfg.window_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def _failure_ratio_locked(self, now: float) -> Tuple[int, float]:
        self._prune(now)
        n = len(self._history)
        if n == 0:
            return 0, 0.0
        failures = sum(1 for _, ok in self._history if not ok)
        return n, failures / n

    def allow_request(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if (
                    self._opened_at is not None
                    and now - self._opened_at >= self._cfg.open_seconds
                ):
                    # Enter half-open and let exactly one probe through.
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._probe_in_flight = True
                    return True
                return False
            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._probe_in_flight:
                    # Another probe is already out; shed new load until it
                    # resolves.
                    return False
                self._probe_in_flight = True
                return True
            return True

    def record(self, success: bool) -> None:
        now = time.monotonic()
        with self._lock:
            self._history.append((now, success))
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._probe_in_flight = False
                if success:
                    self._state = CircuitBreakerState.CLOSED
                    self._opened_at = None
                else:
                    self._state = CircuitBreakerState.OPEN
                    self._opened_at = now
                return

            if self._state == CircuitBreakerState.CLOSED:
                n, ratio = self._failure_ratio_locked(now)
                if (
                    n >= self._cfg.min_requests_for_trip
                    and ratio >= self._cfg.failure_ratio_threshold
                ):
                    self._state = CircuitBreakerState.OPEN
                    self._opened_at = now

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            n, ratio = self._failure_ratio_locked(now)
            return {
                "state": self._state,
                "window_size": n,
                "failure_ratio": round(ratio, 3),
                "threshold": self._cfg.failure_ratio_threshold,
                "window_seconds": self._cfg.window_seconds,
                "opened_at_monotonic": self._opened_at,
            }


# Module-level singleton used by the completions handler. Replace or wrap
# this if tests need isolated state.
sdk_circuit_breaker = CircuitBreaker()
