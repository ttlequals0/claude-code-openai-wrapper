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
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(
            cli, ClaudeCodeCLI
        )
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
