"""In-process record of the Claude subscription quota reported by the CLI.

The Agent SDK emits a RateLimitEvent whenever the CLI's rate-limit state
changes, carrying the status, utilization and reset time of whichever window
is binding. That is the same data claude-quota-proxy scrapes from
anthropic-ratelimit-unified-* response headers, delivered in-band, so the
wrapper needs no proxy in front of the API to know where it stands.

Windows are tracked independently because the CLI reports whichever one is
currently binding: a five_hour rejection does not clear a known seven_day
utilization, and vice versa.

State is per-process. With UVICORN_WORKERS > 1 each worker learns only from
the traffic it serves, so a snapshot is one worker's view. Same caveat as the
circuit breaker; a shared store would be needed to change it.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Source: claude_agent_sdk.types.RateLimitType.
OVERAGE = "overage"

# Windows go stale when traffic is quiet and no event has arrived.
_DEFAULT_STALE_AFTER_SECONDS = 900

# Refresh cadence. The bundled CLI has no usage subcommand, so a probe is a
# real inference call that spends the quota it measures: hence a request-count
# trigger with a time floor, rather than a plain interval.
_DEFAULT_PROBE_EVERY_N_REQUESTS = 100
_DEFAULT_PROBE_MIN_INTERVAL_SECONDS = 300


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def quota_enforcement_enabled() -> bool:
    """Whether to refuse requests with 429 while a window is rejected.

    Off by default: refusing is a behaviour change for existing callers, and
    the accurate Retry-After on real upstream rejections ships either way.
    """
    return _env_bool("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", False)


def probe_every_n_requests() -> int:
    """Requests between refresh probes. 0 disables probing."""
    return _env_int("WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS", _DEFAULT_PROBE_EVERY_N_REQUESTS)


def probe_min_interval_seconds() -> int:
    """Floor between probes, so a burst cannot trigger a run of them."""
    return _env_int("WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS", _DEFAULT_PROBE_MIN_INTERVAL_SECONDS)


def _iso(unix_seconds: Optional[float]) -> Optional[str]:
    if unix_seconds is None:
        return None
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).isoformat()


@dataclass
class QuotaWindow:
    """Last reported state of one rate-limit window."""

    rate_limit_type: str
    status: str
    utilization: Optional[float] = None
    resets_at: Optional[int] = None
    source: str = "passive"
    observed_at: float = field(default_factory=time.time)

    def seconds_until_reset(self, now: float) -> Optional[int]:
        if self.resets_at is None:
            return None
        return max(0, int(self.resets_at - now))

    def as_dict(self, now: float, stale_after: int) -> Dict[str, Any]:
        return {
            "status": self.status,
            "utilization": (
                round(self.utilization, 4) if isinstance(self.utilization, float) else None
            ),
            "resets_at": self.resets_at,
            "resets_at_iso": _iso(self.resets_at),
            "seconds_until_reset": self.seconds_until_reset(now),
            "observed_at": _iso(self.observed_at),
            "source": self.source,
            "stale": (now - self.observed_at) > stale_after,
        }


class QuotaTracker:
    """Latest quota state per window, fed from SDK rate-limit events.

    Thread-safe. ``record()`` runs on the SDK message stream; ``snapshot()``
    serves /v1/usage.
    """

    def __init__(self, stale_after_seconds: int | None = None) -> None:
        self._lock = threading.Lock()
        self._windows: Dict[str, QuotaWindow] = {}
        self._requests_since_probe = 0
        self._stale_after = (
            stale_after_seconds
            if stale_after_seconds is not None
            else _env_int("WRAPPER_QUOTA_STALE_AFTER_SECONDS", _DEFAULT_STALE_AFTER_SECONDS)
        )

    def record(self, info: Any, source: str = "passive") -> None:
        """Record a RateLimitInfo, as the SDK dataclass or an equivalent dict.

        A single event describes the binding window and, separately, the
        overage pool; both are stored so blocking can tell whether paid burst
        capacity is still available.
        """
        get = info.get if isinstance(info, dict) else lambda k, d=None: getattr(info, k, d)

        status = get("status")
        if not isinstance(status, str):
            return

        now = time.time()
        rate_limit_type = get("rate_limit_type") or "unknown"
        window = QuotaWindow(
            rate_limit_type=rate_limit_type,
            status=status,
            utilization=get("utilization"),
            resets_at=get("resets_at"),
            source=source,
            observed_at=now,
        )

        overage_status = get("overage_status")
        overage = None
        if isinstance(overage_status, str):
            overage = QuotaWindow(
                rate_limit_type=OVERAGE,
                status=overage_status,
                resets_at=get("overage_resets_at"),
                source=source,
                observed_at=now,
            )

        with self._lock:
            self._windows[rate_limit_type] = window
            if overage is not None:
                self._windows[OVERAGE] = overage

    def note_request(self) -> None:
        """Count a request towards the next refresh probe."""
        with self._lock:
            self._requests_since_probe += 1

    def probe_due(self, every_n: int) -> bool:
        """True, and resets the counter, once every_n requests have passed."""
        if every_n <= 0:
            return False
        with self._lock:
            if self._requests_since_probe < every_n:
                return False
            self._requests_since_probe = 0
            return True

    def blocked_until(self) -> Optional[int]:
        """Unix reset time of the binding rejected window, else None.

        Overage suppresses blocking only when it was observed no earlier than
        the rejected window and still has room; a rejected or stale burst pool
        is no help.
        """
        now = time.time()
        with self._lock:
            rejected = [
                w
                for key, w in self._windows.items()
                if key != OVERAGE
                and w.status == "rejected"
                and (w.resets_at is None or w.resets_at > now)
            ]
            if not rejected:
                return None

            overage = self._windows.get(OVERAGE)
            newest_rejection = max(w.observed_at for w in rejected)
            if (
                overage is not None
                and overage.status != "rejected"
                and overage.observed_at >= newest_rejection
            ):
                return None

            resets = [w.resets_at for w in rejected if w.resets_at is not None]

        # No reset time reported: blocked, but the caller cannot be told when.
        return max(resets) if resets else 0

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        blocked_until = self.blocked_until()
        with self._lock:
            windows = {key: w.as_dict(now, self._stale_after) for key, w in self._windows.items()}
        return {
            "blocked": blocked_until is not None,
            "blocked_until": blocked_until or None,
            "blocked_until_iso": _iso(blocked_until) if blocked_until else None,
            "seconds_until_reset": (max(0, int(blocked_until - now)) if blocked_until else None),
            "windows": windows,
            "observed_windows": len(windows),
        }


quota_tracker = QuotaTracker()
