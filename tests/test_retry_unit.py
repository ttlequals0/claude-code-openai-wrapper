"""Unit tests for retry logic module."""

import pytest
from src.retry import RetryConfig, RetryState


class TestRetryConfig:
    """Tests for RetryConfig defaults."""

    def test_default_config(self):
        config = RetryConfig()
        assert config.max_retries == 10
        assert config.base_delay_ms == 500
        assert config.max_delay_ms == 30_000
        assert config.enable_model_fallback is True

    def test_custom_config(self):
        config = RetryConfig(max_retries=3, base_delay_ms=100, enable_model_fallback=False)
        assert config.max_retries == 3
        assert config.base_delay_ms == 100
        assert config.enable_model_fallback is False


class TestRetryState:
    """Tests for RetryState logic."""

    def test_initial_state(self):
        state = RetryState()
        assert state.attempt == 0
        assert state.consecutive_529s == 0
        assert state.fallback_model is None

    def test_should_retry_429(self):
        state = RetryState()
        assert state.should_retry(status_code=429) is True

    def test_should_retry_529(self):
        state = RetryState()
        assert state.should_retry(status_code=529) is True

    def test_should_retry_500(self):
        state = RetryState()
        assert state.should_retry(status_code=500) is True

    def test_should_not_retry_200(self):
        state = RetryState()
        assert state.should_retry(status_code=200) is False

    def test_should_not_retry_404(self):
        state = RetryState()
        assert state.should_retry(status_code=404) is False

    def test_should_retry_timeout_error(self):
        state = RetryState()
        assert state.should_retry(error=Exception("Connection timeout")) is True

    def test_should_not_retry_generic_error(self):
        state = RetryState()
        assert state.should_retry(error=Exception("Invalid input")) is False

    def test_should_not_retry_400(self):
        state = RetryState()
        assert state.should_retry(status_code=400) is False

    def test_should_retry_context_overflow(self):
        state = RetryState()
        assert state.should_retry(error=Exception("context overflow: message too long")) is True

    def test_max_retries_exhausted(self):
        config = RetryConfig(max_retries=2)
        state = RetryState(config=config)
        state.attempt = 2
        assert state.should_retry(status_code=429) is False

    def test_record_attempt_tracks_529s(self):
        state = RetryState()
        state.record_attempt(status_code=529)
        assert state.consecutive_529s == 1
        assert state.attempt == 1

        state.record_attempt(status_code=529)
        assert state.consecutive_529s == 2

        state.record_attempt(status_code=429)
        assert state.consecutive_529s == 0  # Reset on non-529

    def test_should_fallback_after_consecutive_529s(self):
        state = RetryState()
        state.consecutive_529s = 3
        assert state.should_fallback("claude-opus-4-6") is True

    def test_should_not_fallback_before_threshold(self):
        state = RetryState()
        state.consecutive_529s = 2
        assert state.should_fallback("claude-opus-4-6") is False

    def test_should_not_fallback_for_non_opus(self):
        state = RetryState()
        state.consecutive_529s = 3
        assert state.should_fallback("claude-sonnet-4-6") is False

    def test_should_not_fallback_when_disabled(self):
        config = RetryConfig(enable_model_fallback=False)
        state = RetryState(config=config)
        state.consecutive_529s = 3
        assert state.should_fallback("claude-opus-4-6") is False

    def test_get_fallback_model(self):
        state = RetryState()
        state.consecutive_529s = 3
        fallback = state.get_fallback_model("claude-opus-4-6")
        assert fallback == "claude-sonnet-4-6"
        assert state.fallback_model == "claude-sonnet-4-6"
        assert state.consecutive_529s == 0  # Reset after fallback

    def test_get_fallback_model_none_for_sonnet(self):
        state = RetryState()
        state.consecutive_529s = 3
        fallback = state.get_fallback_model("claude-sonnet-4-6")
        assert fallback is None

    def test_calculate_delay_exponential(self):
        state = RetryState(config=RetryConfig(base_delay_ms=1000))
        state.attempt = 0
        delay0 = state.calculate_delay()
        state.attempt = 1
        delay1 = state.calculate_delay()
        state.attempt = 2
        delay2 = state.calculate_delay()
        # Each delay should roughly double (with jitter)
        assert delay1 > delay0
        assert delay2 > delay1

    def test_calculate_delay_capped(self):
        config = RetryConfig(base_delay_ms=1000, max_delay_ms=5000)
        state = RetryState(config=config)
        state.attempt = 20  # Very high attempt
        delay = state.calculate_delay()
        # Should be capped at max + jitter (max 25% jitter)
        assert delay <= 5.0 * 1.25

    def test_calculate_delay_respects_retry_after(self):
        state = RetryState(config=RetryConfig(base_delay_ms=100))
        state.attempt = 0
        delay = state.calculate_delay(retry_after=10.0)
        assert delay >= 10.0  # Must be at least retry-after value
