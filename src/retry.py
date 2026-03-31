"""
Retry logic with exponential backoff and model fallback.

Patterns sourced from open-sourced Claude Code CLI (src/services/api/withRetry.ts).
"""

import asyncio
import logging
import random
from typing import Optional

from src.constants import MODEL_FALLBACK_MAP

logger = logging.getLogger(__name__)

# Retry configuration (matches Claude Code source)
DEFAULT_MAX_RETRIES = 10
BASE_DELAY_MS = 500
MAX_DELAY_MS = 30_000
MAX_CONSECUTIVE_529_FOR_FALLBACK = 3


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay_ms: int = BASE_DELAY_MS,
        max_delay_ms: int = MAX_DELAY_MS,
        enable_model_fallback: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.enable_model_fallback = enable_model_fallback


class RetryState:
    """Tracks retry state across attempts for a single request."""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.attempt = 0
        self.consecutive_529s = 0
        self.fallback_model: Optional[str] = None

    def calculate_delay(self, retry_after: Optional[float] = None) -> float:
        """Calculate delay with exponential backoff and jitter.

        If a retry-after header value is provided, use it as a minimum.
        """
        # Exponential backoff: base * 2^attempt
        exp_delay = self.config.base_delay_ms * (2 ** self.attempt)
        # Cap at max delay
        exp_delay = min(exp_delay, self.config.max_delay_ms)
        # Add jitter (0-25% of delay)
        jitter = random.uniform(0, exp_delay * 0.25)
        delay_ms = exp_delay + jitter

        # If retry-after is provided, use the larger value
        if retry_after is not None:
            retry_after_ms = retry_after * 1000
            delay_ms = max(delay_ms, retry_after_ms)

        return delay_ms / 1000  # Return seconds

    def should_retry(self, status_code: Optional[int] = None, error: Optional[Exception] = None) -> bool:
        """Determine if the request should be retried."""
        if self.attempt >= self.config.max_retries:
            return False

        if status_code is not None:
            if status_code in (429, 529):
                return True
            if status_code >= 500:
                return True
            if status_code == 401:
                return True

        if error is not None:
            error_str = str(error).lower()
            # Network errors are retryable
            if any(term in error_str for term in ["timeout", "connection", "econnreset", "epipe"]):
                return True
            # Context overflow (400) -- only retry if the error message indicates it
            if "context" in error_str and ("overflow" in error_str or "too long" in error_str):
                return True

        return False

    def record_attempt(self, status_code: Optional[int] = None) -> None:
        """Record an attempt and track consecutive 529s."""
        self.attempt += 1

        if status_code == 529:
            self.consecutive_529s += 1
        else:
            self.consecutive_529s = 0

    def should_fallback(self, model: str) -> bool:
        """Check if we should fall back to a faster model after repeated 529s."""
        if not self.config.enable_model_fallback:
            return False
        if self.consecutive_529s < MAX_CONSECUTIVE_529_FOR_FALLBACK:
            return False
        return model in MODEL_FALLBACK_MAP

    def get_fallback_model(self, model: str) -> Optional[str]:
        """Get the fallback model for the given model."""
        if self.should_fallback(model):
            fallback = MODEL_FALLBACK_MAP.get(model)
            if fallback:
                self.fallback_model = fallback
                logger.warning(
                    f"Falling back from {model} to {fallback} after "
                    f"{self.consecutive_529s} consecutive 529 errors"
                )
                self.consecutive_529s = 0
            return fallback
        return None


async def retry_delay(state: RetryState, retry_after: Optional[float] = None) -> None:
    """Wait for the calculated retry delay."""
    delay = state.calculate_delay(retry_after)
    logger.info(f"Retry attempt {state.attempt}/{state.config.max_retries}, waiting {delay:.1f}s")
    await asyncio.sleep(delay)
