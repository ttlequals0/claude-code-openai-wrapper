"""Unit tests for the SDK-error -> HTTP-response translation helpers.

These cover the OpenAI-shape outputs we produce when parse_claude_message
raises ClaudeResultError, so an error_max_turns from the Claude Agent SDK
never ships as a 200 with the literal string '[Request interrupted by user]'
as message content.
"""

import json

from src.claude_cli import ClaudeResultError
from src.main import (
    _build_error_max_turns_response,
    _build_sdk_error_response,
    _handle_claude_result_error,
)


def _body(response):
    return json.loads(response.body)


class TestErrorMaxTurnsResponse:
    def test_returns_200_with_finish_reason_length_and_empty_content(self):
        err = ClaudeResultError(
            subtype="error_max_turns",
            num_turns=2,
            errors=None,
            stop_reason=None,
            error_message=None,
        )
        resp = _build_error_max_turns_response("req-1", "claude-sonnet-4-6", err)

        assert resp.status_code == 200
        body = _body(resp)
        assert body["id"] == "req-1"
        assert body["model"] == "claude-sonnet-4-6"
        assert body["choices"][0]["finish_reason"] == "length"
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert body["choices"][0]["message"]["content"] == ""
        # Sentinel must not appear in the serialized body under any field.
        assert "Request interrupted by user" not in json.dumps(body)


class TestSdkErrorResponse:
    def test_returns_502_with_structured_error_body(self):
        err = ClaudeResultError(
            subtype="error_during_execution",
            num_turns=0,
            errors=["upstream timeout"],
            stop_reason=None,
            error_message=None,
        )
        resp = _build_sdk_error_response("req-2", "claude-sonnet-4-6", err)

        assert resp.status_code == 502
        body = _body(resp)
        assert body["error"]["type"] == "upstream_sdk_error"
        assert body["error"]["code"] == "error_during_execution"
        assert body["error"]["message"] == "upstream timeout"


class TestHandleClaudeResultError:
    def test_error_max_turns_routes_to_length_finish_reason(self):
        err = ClaudeResultError(subtype="error_max_turns", num_turns=2)
        resp = _handle_claude_result_error("req-3", "claude-opus-4-6", err)

        assert resp.status_code == 200
        body = _body(resp)
        assert body["choices"][0]["finish_reason"] == "length"

    def test_other_errors_route_to_502(self):
        err = ClaudeResultError(
            subtype="error_during_execution",
            num_turns=0,
            error_message="boom",
        )
        resp = _handle_claude_result_error("req-4", "claude-opus-4-6", err)

        assert resp.status_code == 502
        assert _body(resp)["error"]["code"] == "error_during_execution"

    def test_generic_is_error_routes_to_502(self):
        # Covers future SDK subtypes that aren't explicitly enumerated.
        err = ClaudeResultError(subtype="something_new", num_turns=1)
        resp = _handle_claude_result_error("req-5", "claude-opus-4-6", err)

        assert resp.status_code == 502
        assert _body(resp)["error"]["code"] == "something_new"


class TestAssistantErrorTaxonomy:
    """AssistantMessage.error literals map to proper HTTP status codes."""

    def test_rate_limit_returns_429_with_retry_after(self):
        err = ClaudeResultError(subtype="assistant_rate_limit", errors=["rate_limit"])
        resp = _handle_claude_result_error("req-rl", "claude-sonnet-4-6", err)
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "30"
        assert _body(resp)["error"]["code"] == "assistant_rate_limit"

    def test_billing_error_returns_402(self):
        err = ClaudeResultError(subtype="assistant_billing_error", errors=["billing_error"])
        resp = _handle_claude_result_error("req-be", "claude-sonnet-4-6", err)
        assert resp.status_code == 402

    def test_authentication_failed_returns_401(self):
        err = ClaudeResultError(
            subtype="assistant_authentication_failed",
            errors=["authentication_failed"],
        )
        resp = _handle_claude_result_error("req-af", "claude-sonnet-4-6", err)
        assert resp.status_code == 401

    def test_invalid_request_returns_400(self):
        err = ClaudeResultError(subtype="assistant_invalid_request", errors=["invalid_request"])
        resp = _handle_claude_result_error("req-ir", "claude-sonnet-4-6", err)
        assert resp.status_code == 400

    def test_server_error_returns_502(self):
        err = ClaudeResultError(subtype="assistant_server_error", errors=["server_error"])
        resp = _handle_claude_result_error("req-se", "claude-sonnet-4-6", err)
        assert resp.status_code == 502


class TestParseClaudeMessageAssistantError:
    """parse_claude_message raises with the assistant_<error> subtype so the
    HTTP layer can map each AssistantMessageError literal to a status code."""

    def test_assistant_rate_limit_raises(self):
        from unittest.mock import MagicMock

        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock()
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(cli, ClaudeCodeCLI)
        messages = [
            {
                "content": [{"type": "text", "text": "partial"}],
                "model": "claude-sonnet-4-6",
                "error": "rate_limit",
            }
        ]
        import pytest

        with pytest.raises(ClaudeResultError) as excinfo:
            cli.parse_claude_message(messages)
        assert excinfo.value.subtype == "assistant_rate_limit"
        assert "rate_limit" in excinfo.value.errors


class TestParseClaudeMessageRateLimitEvent:
    """A rate-limit event nests its fields under rate_limit_info. The old
    check looked for them at the top level, so it never fired."""

    @staticmethod
    def _parse(messages):
        from unittest.mock import MagicMock

        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock()
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(cli, ClaudeCodeCLI)
        return cli.parse_claude_message(messages)

    def test_rejected_event_raises_with_reset_details(self):
        import pytest

        reset = 1788135731
        messages = [
            {
                "rate_limit_info": {
                    "status": "rejected",
                    "resets_at": reset,
                    "rate_limit_type": "seven_day",
                },
                "session_id": "s-1",
                "uuid": "u-1",
            }
        ]
        with pytest.raises(ClaudeResultError) as excinfo:
            self._parse(messages)
        assert excinfo.value.subtype == "assistant_rate_limit"
        assert excinfo.value.resets_at == reset
        assert excinfo.value.rate_limit_type == "seven_day"

    def test_allowed_event_does_not_raise(self):
        messages = [
            {
                "rate_limit_info": {"status": "allowed", "rate_limit_type": "five_hour"},
                "session_id": "s-1",
                "uuid": "u-1",
            },
            {"subtype": "success", "result": "hello"},
        ]
        assert self._parse(messages) == "hello"


class TestRetryAfterDerivation:
    """Retry-After comes from the upstream reset, capped so a multi-day
    window cannot tell a client to sleep through it."""

    def test_uses_the_reported_reset(self):
        import time

        from src.main import _retry_after_seconds

        assert 40 <= _retry_after_seconds(int(time.time()) + 45) <= 45

    def test_caps_a_long_window(self):
        import time

        from src.main import _retry_after_seconds

        assert _retry_after_seconds(int(time.time()) + 604800) == 3600

    def test_falls_back_when_no_reset_reported(self):
        from src.main import _retry_after_seconds

        assert _retry_after_seconds(None) == 30

    def test_rate_limit_response_carries_reset_detail(self):
        import time

        from src.main import _build_assistant_error_response, _retry_after_seconds

        reset = int(time.time()) + 900
        err = ClaudeResultError(
            subtype="assistant_rate_limit",
            errors=["rate_limit"],
            resets_at=reset,
            rate_limit_type="five_hour",
        )
        response = _build_assistant_error_response("req-1", "claude-opus-5", err)
        body = _body(response)["error"]
        assert response.status_code == 429
        assert response.headers["retry-after"] == str(_retry_after_seconds(reset))
        assert body["resets_at"] == reset
        assert body["rate_limit_type"] == "five_hour"

    def test_rate_limit_response_omits_detail_without_a_reset(self):
        from src.main import _build_assistant_error_response

        err = ClaudeResultError(subtype="assistant_rate_limit", errors=["rate_limit"])
        response = _build_assistant_error_response("req-2", "claude-opus-5", err)
        body = _body(response)["error"]
        assert response.headers["retry-after"] == "30"
        assert "resets_at" not in body


class TestCliAuthFailureToFourOhOne:
    """Defense-in-depth: when ClaudeResultError carries CLI auth markers in
    its stderr_tail or error_message, _build_sdk_error_response must return
    HTTP 401 instead of 502, with an OpenAI-shaped authentication_error body.
    """

    def test_sdk_error_with_auth_marker_in_stderr_maps_to_401(self):
        err = ClaudeResultError(
            subtype="error_during_execution",
            num_turns=0,
            errors=None,
            stop_reason=None,
            error_message=None,
            stderr_tail="Not logged in - Please run /login",
        )
        resp = _build_sdk_error_response("req-cli-auth", "claude-sonnet-4-6", err)
        assert resp.status_code == 401
        body = _body(resp)
        assert body["error"]["type"] == "authentication_error"
        assert body["error"]["code"] == "claude_cli_not_authenticated"

    def test_sdk_error_with_invalid_api_key_in_message_maps_to_401(self):
        err = ClaudeResultError(
            subtype="error_during_execution",
            errors=["Invalid API key"],
            error_message="Invalid API key",
        )
        resp = _build_sdk_error_response("req-cli-key", "claude-sonnet-4-6", err)
        assert resp.status_code == 401
        body = _body(resp)
        assert body["error"]["type"] == "authentication_error"

    def test_sdk_error_without_auth_marker_still_502(self):
        err = ClaudeResultError(
            subtype="error_during_execution",
            errors=["upstream timeout"],
            stderr_tail="connection refused",
        )
        resp = _build_sdk_error_response("req-generic", "claude-sonnet-4-6", err)
        assert resp.status_code == 502
        body = _body(resp)
        assert body["error"]["type"] == "upstream_sdk_error"

    def test_sdk_error_with_auth_marker_seeds_cli_health(self):
        import src.auth

        src.auth.cli_health.mark_ok()
        assert src.auth.cli_health.ok is True

        err = ClaudeResultError(
            subtype="error_during_execution",
            stderr_tail="Not logged in - Please run /login",
        )
        _build_sdk_error_response("req-cli-seed", "claude-sonnet-4-6", err)
        assert src.auth.cli_health.ok is False
        assert src.auth.cli_health.error_kind == "auth_failure"
