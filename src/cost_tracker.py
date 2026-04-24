"""
Cost tracking for Claude API usage.

Calculates estimated costs per request and accumulates per session.
Pricing sourced from open-sourced Claude Code CLI (src/utils/modelCost.ts).
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from src.constants import MODEL_PRICING, WEB_SEARCH_COST_USD, SESSION_MAX_AGE_MINUTES

logger = logging.getLogger(__name__)

# Default pricing tier (Sonnet) for unknown models
_DEFAULT_PRICING = MODEL_PRICING.get(
    "claude-sonnet-4-6",
    {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
)

_KEY_INPUT = "input"
_KEY_OUTPUT = "output"
_KEY_CACHE_READ = "cache_read"
_KEY_CACHE_WRITE = "cache_write"


@dataclass
class UsageRecord:
    """Token usage for a single request."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    web_search_requests: int = 0


@dataclass
class SessionCost:
    """Accumulated cost for a session."""

    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_web_search_requests: int = 0
    request_count: int = 0
    model_usage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


def calculate_cost(model: str, usage: UsageRecord) -> float:
    """Calculate the cost in USD for a given model and usage."""
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)

    cost = 0.0
    cost += (usage.input_tokens / 1_000_000) * pricing[_KEY_INPUT]
    cost += (usage.output_tokens / 1_000_000) * pricing[_KEY_OUTPUT]
    cost += (usage.cache_read_tokens / 1_000_000) * pricing[_KEY_CACHE_READ]
    cost += (usage.cache_creation_tokens / 1_000_000) * pricing[_KEY_CACHE_WRITE]
    cost += usage.web_search_requests * WEB_SEARCH_COST_USD

    return cost


class CostTracker:
    """Tracks costs per session. Uses asyncio.Lock for async-safe access."""

    def __init__(self, max_age_minutes: int = SESSION_MAX_AGE_MINUTES):
        self._sessions: Dict[str, SessionCost] = {}
        self._lock = asyncio.Lock()
        self._max_age_seconds = max_age_minutes * 60

    async def record_usage(
        self,
        session_id: str,
        model: str,
        usage: UsageRecord,
    ) -> float:
        """Record usage for a session. Returns the cost for this request."""
        cost = calculate_cost(model, usage)

        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionCost()

            session = self._sessions[session_id]
            session.total_cost_usd += cost
            session.total_input_tokens += usage.input_tokens
            session.total_output_tokens += usage.output_tokens
            session.total_cache_read_tokens += usage.cache_read_tokens
            session.total_cache_creation_tokens += usage.cache_creation_tokens
            session.total_web_search_requests += usage.web_search_requests
            session.request_count += 1
            session.last_updated = time.time()

            if model not in session.model_usage:
                session.model_usage[model] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "requests": 0,
                }
            session.model_usage[model]["input_tokens"] += usage.input_tokens
            session.model_usage[model]["output_tokens"] += usage.output_tokens
            session.model_usage[model]["cost_usd"] += cost
            session.model_usage[model]["requests"] += 1

        logger.debug(
            f"Session {session_id}: request cost=${cost:.6f}, "
            f"total=${session.total_cost_usd:.6f}"
        )
        return cost

    async def cleanup_expired(self) -> int:
        """Remove sessions older than max_age. Returns count of removed sessions."""
        now = time.time()
        async with self._lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if (now - s.last_updated) > self._max_age_seconds
            ]
            for sid in expired:
                del self._sessions[sid]
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired cost tracker sessions")
            return len(expired)

    async def get_session_cost(self, session_id: str) -> Optional[SessionCost]:
        """Get accumulated cost for a session."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get a summary dict for a session's costs."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return {"session_id": session_id, "total_cost_usd": 0.0, "request_count": 0}

            return {
                "session_id": session_id,
                "total_cost_usd": round(session.total_cost_usd, 6),
                "total_input_tokens": session.total_input_tokens,
                "total_output_tokens": session.total_output_tokens,
                "total_cache_read_tokens": session.total_cache_read_tokens,
                "total_cache_creation_tokens": session.total_cache_creation_tokens,
                "total_web_search_requests": session.total_web_search_requests,
                "request_count": session.request_count,
                "model_usage": dict(session.model_usage),
            }

    async def delete_session(self, session_id: str) -> bool:
        """Remove cost tracking for a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def get_all_sessions_summary(self) -> Dict[str, Any]:
        """Get cost summary across all sessions."""
        async with self._lock:
            total_cost = sum(s.total_cost_usd for s in self._sessions.values())
            total_requests = sum(s.request_count for s in self._sessions.values())
            return {
                "active_sessions": len(self._sessions),
                "total_cost_usd": round(total_cost, 6),
                "total_requests": total_requests,
            }


# Global singleton instance
cost_tracker = CostTracker()
