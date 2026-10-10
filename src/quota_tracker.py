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
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# Source: claude_agent_sdk.types.RateLimitType.
OVERAGE = "overage"

# Text shapes the CLI uses when the subscription quota is exhausted. Shared
# by the auth-probe classifier and the completion error path. "session limit"
# is the wording of the rolling window ("You've hit your session limit"),
# which the older marker list missed.
QUOTA_ERROR_TEXT_MARKERS = (
    "usage limit",
    "session limit",
    "rate limit",
    "rate_limit",
    "quota",
)


def is_quota_error_text(blob: str) -> bool:
    """Whether an error's prose describes an exhausted quota."""
    lowered = (blob or "").lower()
    return any(marker in lowered for marker in QUOTA_ERROR_TEXT_MARKERS)


# Tighter than QUOTA_ERROR_TEXT_MARKERS: names an account-level limit
# specifically, not just any mention of "rate limit" or "quota". Used to
# gate recording a rejection that carries no parsed reset time, so a bare
# 429 or generic "rate limit" text does not mark a window rejected on a
# guess.
ACCOUNT_LIMIT_TEXT_MARKERS = (
    "session limit",
    "usage limit",
    "weekly limit",
    "limit reached",
)


def is_account_limit_text(blob: str) -> bool:
    """Whether prose names an account-level limit by phrase."""
    lowered = (blob or "").lower()
    return any(marker in lowered for marker in ACCOUNT_LIMIT_TEXT_MARKERS)


# "resets 6pm (UTC)" / "resets at 11:30pm (UTC)" / "resets 10:50am (UTC)".
# The trailing "(ZONE)" is optional and, when present, only a zone we know is
# UTC is trusted ("UTC", "GMT", "Etc/UTC"); any other named zone is not
# something we can convert correctly, so it falls back to no reset rather
# than silently misreading it as UTC.
_RESET_CLOCK_RE = re.compile(
    r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b(?:\s*\(([^)]*)\))?",
    re.IGNORECASE,
)

_UTC_ZONE_NAMES = frozenset({"UTC", "GMT", "ETC/UTC"})

# Grace window: the CLI's clock and ours can be a few seconds apart, so a
# reset named for a moment just in the past is still today's.
_ROLLOVER_GRACE_SECONDS = 60


def parse_reset_clock_time(text: str, now: Optional[float] = None) -> Optional[int]:
    """Epoch seconds for a CLI reset phrase like 'resets 6pm (UTC)'.

    Takes the next future occurrence of the named UTC hour, rolling to
    tomorrow when it has already passed today by more than a minute. Returns
    None when the text names no reset time, or names a timezone other than
    UTC.
    """
    match = _RESET_CLOCK_RE.search(text or "")
    if not match:
        return None
    tz_name = match.group(4)
    if tz_name is not None and tz_name.strip().upper() not in _UTC_ZONE_NAMES:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour < 1 or hour > 12 or minute > 59:
        return None
    hour %= 12
    if match.group(3).lower() == "pm":
        hour += 12
    now_ts = time.time() if now is None else now
    base = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() < now_ts - _ROLLOVER_GRACE_SECONDS:
        candidate += timedelta(days=1)
    return int(candidate.timestamp())


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
    """Last reported state of one rate-limit window.

    ``status`` is None for a window the CLI did not name as the binding one:
    it reports a status for the representative window only, and inferring one
    from utilization would be inventing data.
    """

    rate_limit_type: str
    status: Optional[str] = None
    utilization: Optional[float] = None
    resets_at: Optional[int] = None
    representative: bool = False
    disabled_reason: Optional[str] = None
    source: str = "passive"
    observed_at: float = field(default_factory=time.time)

    def seconds_until_reset(self, now: float) -> Optional[int]:
        if self.resets_at is None:
            return None
        return max(0, int(self.resets_at - now))

    def is_active_rejection(self, now: float, stale_after: int) -> bool:
        """Whether this window is still a live 'rejected' block.

        A rejection with a known reset expires at that reset; one with no
        reset (the CLI named no reset hour) expires after ``stale_after``
        from when it was observed, so it does not block forever.
        """
        if self.status != "rejected":
            return False
        if self.resets_at is not None:
            return self.resets_at > now
        return (now - self.observed_at) <= stale_after

    def as_dict(self, now: float, stale_after: int) -> Dict[str, Any]:
        # A rejection that has expired (past reset, or stale with no reset)
        # must not linger as "rejected" in /v1/usage.
        status = self.status
        if status == "rejected" and not self.is_active_rejection(now, stale_after):
            status = None
        payload = {
            "status": status,
            "utilization": (
                round(self.utilization, 4) if isinstance(self.utilization, float) else None
            ),
            "resets_at": self.resets_at,
            "resets_at_iso": _iso(self.resets_at),
            "seconds_until_reset": self.seconds_until_reset(now),
            "representative": self.representative,
            "observed_at": _iso(self.observed_at),
            "source": self.source,
            "stale": (now - self.observed_at) > stale_after,
        }
        if self.disabled_reason:
            payload["disabled_reason"] = self.disabled_reason
        return payload


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

        The SDK models only the representative window plus the overage pool,
        but the CLI sends every window under raw["unifiedWindows"], and that
        is the only place utilization appears. Reading just the modelled
        fields loses the weekly window entirely and reports a null
        utilization for everything.
        """
        get = info.get if isinstance(info, dict) else lambda k, d=None: getattr(info, k, d)

        status = get("status")
        if not isinstance(status, str):
            return

        now = time.time()
        representative = get("rate_limit_type") or "unknown"
        raw = get("raw") or {}
        unified = raw.get("unifiedWindows") if isinstance(raw, dict) else None

        windows = {}
        if isinstance(unified, dict):
            for name, data in unified.items():
                if not isinstance(data, dict):
                    continue
                windows[name] = QuotaWindow(
                    rate_limit_type=name,
                    status=status if name == representative else None,
                    utilization=data.get("utilization"),
                    resets_at=data.get("resetsAt"),
                    representative=(name == representative),
                    source=source,
                    observed_at=now,
                )

        with self._lock:
            # Fall back to the modelled fields for the representative window
            # when unifiedWindows is absent or does not mention it. An
            # error-text record carries no utilization at all; rather than
            # wipe out a utilization already known for this window from live
            # traffic, keep the last observed value.
            if representative not in windows:
                utilization = get("utilization")
                if utilization is None and source == "error_text":
                    previous = self._windows.get(representative)
                    if previous is not None:
                        utilization = previous.utilization
                windows[representative] = QuotaWindow(
                    rate_limit_type=representative,
                    status=status,
                    utilization=utilization,
                    resets_at=get("resets_at"),
                    representative=True,
                    source=source,
                    observed_at=now,
                )

            overage_status = get("overage_status")
            if isinstance(overage_status, str):
                windows[OVERAGE] = QuotaWindow(
                    rate_limit_type=OVERAGE,
                    status=overage_status,
                    resets_at=get("overage_resets_at"),
                    disabled_reason=get("overage_disabled_reason"),
                    source=source,
                    observed_at=now,
                )

            # An error-text record is synthesised from one window's prose,
            # not a full CLI payload; clear representative on any other
            # window still carrying it from an earlier event, so
            # binding_window stays unambiguous.
            if source == "error_text":
                for key, existing in self._windows.items():
                    if key != OVERAGE and key not in windows:
                        existing.representative = False

            self._windows.update(windows)

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
                if key != OVERAGE and w.is_active_rejection(now, self._stale_after)
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
            stored = dict(self._windows)
            windows = {key: w.as_dict(now, self._stale_after) for key, w in stored.items()}

        # The window nearest its cap is the one that will cut you off, and it
        # is not always the one the CLI named. Surfacing it here means callers
        # do not have to scan and compare every window themselves.
        rated = [
            w
            for key, w in stored.items()
            if key != OVERAGE and isinstance(w.utilization, (int, float))
        ]
        closest = max(rated, key=lambda w: w.utilization) if rated else None
        representative = next(
            (key for key, w in stored.items() if w.representative and key != OVERAGE), None
        )

        return {
            "blocked": blocked_until is not None,
            "blocked_until": blocked_until or None,
            "blocked_until_iso": _iso(blocked_until) if blocked_until else None,
            "seconds_until_reset": (max(0, int(blocked_until - now)) if blocked_until else None),
            "binding_window": representative,
            "closest_to_limit": (
                {
                    "window": closest.rate_limit_type,
                    "utilization": round(float(closest.utilization), 4),
                    "resets_at": closest.resets_at,
                    "resets_at_iso": _iso(closest.resets_at),
                    "seconds_until_reset": closest.seconds_until_reset(now),
                }
                if closest is not None
                else None
            ),
            "windows": windows,
            "observed_windows": len(windows),
        }


quota_tracker = QuotaTracker()
