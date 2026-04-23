"""Unit tests for src.main._kv log-line formatter.

The wrapper's default logging format is plain text and drops extras.
``_kv`` exists so we can serialize structured fields INTO the message string
itself without reaching for a full JSON logger.
"""

from src.main import _kv


class TestKvFormatter:
    def test_basic_event_only(self):
        assert _kv("circuit_breaker_open") == "circuit_breaker_open"

    def test_simple_key_value(self):
        assert (
            _kv("completion_result", num_turns=2, subtype="success")
            == "completion_result num_turns=2 subtype=success"
        )

    def test_none_values_are_skipped(self):
        # None extras would just spam the log line if kept; drop them.
        out = _kv("claude_sdk_error", subtype="error_max_turns", stop_reason=None)
        assert "stop_reason" not in out
        assert out == "claude_sdk_error subtype=error_max_turns"

    def test_values_with_whitespace_are_quoted(self):
        # grep for `key=value` must keep working even when the value has spaces.
        out = _kv("claude_sdk_error", error_message="boom boom")
        assert "error_message='boom boom'" in out

    def test_equals_in_value_is_quoted(self):
        out = _kv("circuit_breaker_open", reason="k=v")
        assert "reason='k=v'" in out

    def test_snapshot_style_kwargs_expansion(self):
        snapshot = {
            "state": "open",
            "window_size": 2,
            "failure_ratio": 1.0,
            "threshold": 0.75,
        }
        out = _kv("circuit_breaker_open", **snapshot)
        assert out.startswith("circuit_breaker_open ")
        assert "state=open" in out
        assert "window_size=2" in out
        assert "failure_ratio=1.0" in out
        assert "threshold=0.75" in out
