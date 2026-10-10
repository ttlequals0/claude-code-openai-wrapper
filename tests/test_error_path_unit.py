"""Unit tests for the SDK-error -> HTTP-response translation helpers.

These cover the OpenAI-shape outputs we produce when parse_claude_message
raises ClaudeResultError, so an error_max_turns from the Claude Agent SDK
never ships as a 200 with the literal string '[Request interrupted by user]'
as message content.
"""

import json
import asyncio

import pytest
from fastapi.testclient import TestClient

from src import auth, main as main_mod
from src.claude_cli import ClaudeResultError
from src.models import ChatCompletionRequest, Message
from src.main import (
    _build_error_max_turns_response,
    _build_sdk_error_response,
    _safe_sdk_result_message,
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

    def test_unsupported_model_cli_version_returns_safe_nonretryable_detail(self):
        raw = (
            "API Error: 400 Claude Code 2.1.277 does not support this model; "
            "version 2.1.280 or newer is required. Run 'claude update', then retry. "
            "Prompt: private prompt"
        )
        err = ClaudeResultError(subtype="success", result=raw)
        resp = _build_sdk_error_response("req-version", "claude-sonnet-4-6", err)
        body = _body(resp)["error"]
        assert resp.status_code == 400
        assert body["type"] == "invalid_request_error"
        assert body["code"] == "claude_cli_upgrade_required"
        assert body["message"] == (
            "The wrapper's bundled Claude Code CLI does not support this model. "
            "Upgrade the wrapper and retry."
        )
        assert "2.1.277" not in json.dumps(body)
        assert "private prompt" not in json.dumps(body)

    def test_expired_oauth_result_uses_existing_static_auth_response(self):
        err = ClaudeResultError(
            subtype="success",
            result="Failed to authenticate: OAuth session expired and could not be refreshed",
        )
        resp = _build_sdk_error_response("req-auth", "claude-sonnet-4-6", err)
        body = _body(resp)["error"]
        assert resp.status_code == 401
        assert body["code"] == "claude_cli_not_authenticated"
        assert "OAuth session expired" not in body["message"]

    def test_auth_result_does_not_store_private_prose_in_cli_health(self):
        raw = (
            "Failed to authenticate: OAuth session expired and could not be refreshed; token=secret"
        )
        err = ClaudeResultError(subtype="success", result=raw)
        try:
            _build_sdk_error_response("req-auth-private", "claude-sonnet-4-6", err)
            assert "secret" not in (auth.cli_health.as_dict()["error_message"] or "")
        finally:
            auth.cli_health.mark_ok()

    def test_flattened_version_error_is_classified_and_sanitized(self):
        raw = (
            "Claude SDK returned an error result: API Error: 400 Claude Code 2.1.277 "
            "does not support this model; version 2.1.280 or newer is required. "
            "Prompt: private prompt token=secret"
        )
        err = ClaudeResultError(subtype="error_during_execution", error_message=raw)
        resp = _build_sdk_error_response("req-version-flat", "claude-sonnet-4-6", err)
        body = _body(resp)["error"]
        assert resp.status_code == 400
        assert body["code"] == "claude_cli_upgrade_required"
        assert "private prompt" not in json.dumps(body)
        assert "secret" not in json.dumps(body)

    def test_unknown_result_prose_is_not_reflected(self):
        err = ClaudeResultError(subtype="success", result="private prompt and token=secret")
        assert _safe_sdk_result_message(err) == "SDK returned an error result (subtype=success)"

    def test_unrelated_refresh_error_is_not_classified_as_auth(self):
        err = ClaudeResultError(subtype="success", result="Cache update could not be refreshed")
        resp = _build_sdk_error_response("req-refresh", "claude-sonnet-4-6", err)
        assert resp.status_code == 502

    def test_version_error_ending_in_401_is_not_classified_as_auth(self):
        err = ClaudeResultError(
            subtype="success",
            result=(
                "API Error: 400 Claude Code 2.1.401 does not support this model; "
                "version 2.1.280 or newer is required."
            ),
        )
        resp = _build_sdk_error_response("req-version-401", "claude-sonnet-4-6", err)
        assert resp.status_code == 400
        assert _body(resp)["error"]["code"] == "claude_cli_upgrade_required"


class TestSafeErrorTransportDetails:
    @pytest.fixture
    def unsupported_model_error(self, monkeypatch):
        raw = (
            "API Error: 400 Claude Code 2.1.277 does not support this model; "
            "version 2.1.280 or newer is required. Prompt: private prompt"
        )

        async def fake_run_completion(**kwargs):
            yield {"subtype": "success", "is_error": True, "result": raw}

        monkeypatch.setattr(main_mod.claude_cli, "run_completion", fake_run_completion)

    def test_streaming_error_uses_safe_upgrade_detail(self, unsupported_model_error):
        request = ChatCompletionRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content="hello")],
            stream=True,
        )
        chunks = asyncio.run(
            _collect_stream(main_mod.generate_streaming_response(request, "req-stream"))
        )
        payload = "".join(chunks)
        assert "claude_cli_upgrade_required" in payload
        assert "private prompt" not in payload

    def test_anthropic_messages_error_uses_safe_upgrade_detail(self, unsupported_model_error):
        response = TestClient(main_mod.app).post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        body = response.json()
        assert response.status_code == 400
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["code"] == "claude_cli_upgrade_required"
        assert "private prompt" not in response.text


async def _collect_stream(stream):
    return [chunk async for chunk in stream]


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

    def test_rate_limit_does_not_record_to_the_circuit_breaker(self):
        """An exhausted account quota is not a service failure; recording it
        to the breaker would trip fail-fast on healthy traffic."""
        from src.circuit_breaker import sdk_circuit_breaker

        before = sdk_circuit_breaker.snapshot()["window_size"]
        err = ClaudeResultError(subtype="assistant_rate_limit", errors=["rate_limit"])
        _handle_claude_result_error("req-rl-cb", "claude-sonnet-4-6", err)
        after = sdk_circuit_breaker.snapshot()["window_size"]
        assert after == before

    def test_real_failure_still_records_to_the_circuit_breaker(self):
        from src.circuit_breaker import sdk_circuit_breaker

        before = sdk_circuit_breaker.snapshot()["window_size"]
        err = ClaudeResultError(subtype="error_during_execution", error_message="boom")
        _handle_claude_result_error("req-real-cb", "claude-opus-4-6", err)
        after = sdk_circuit_breaker.snapshot()["window_size"]
        assert after == before + 1


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

    def test_assistant_rate_limit_parses_reset_from_content_and_records_it(self):
        """The literal error='rate_limit' path previously raised with
        resets_at=None and never recorded the rejection, so /v1/usage never
        learned about it. The reset hour lives in the content text blocks."""
        from unittest.mock import MagicMock, patch

        from src.claude_cli import ClaudeCodeCLI
        from src.quota_tracker import QuotaTracker

        cli = MagicMock()
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(cli, ClaudeCodeCLI)
        messages = [
            {
                "content": [
                    {"type": "text", "text": "You've hit your session limit · resets 6pm (UTC)"}
                ],
                "model": "claude-sonnet-4-6",
                "error": "rate_limit",
            }
        ]
        fresh = QuotaTracker()
        with patch("src.claude_cli.quota_tracker", fresh):
            with pytest.raises(ClaudeResultError) as excinfo:
                cli.parse_claude_message(messages)
        assert excinfo.value.resets_at is not None
        assert excinfo.value.rate_limit_type == "five_hour"
        window = fresh.snapshot()["windows"]["five_hour"]
        assert window["status"] == "rejected"
        assert window["resets_at"] == excinfo.value.resets_at

    def test_assistant_rate_limit_with_account_limit_wording_and_no_reset_still_records(self):
        """No reset found, but the content names an account limit: still
        record the rejection with resets_at=None so /v1/usage shows it."""
        from unittest.mock import MagicMock, patch

        from src.claude_cli import ClaudeCodeCLI
        from src.quota_tracker import QuotaTracker

        cli = MagicMock()
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(cli, ClaudeCodeCLI)
        messages = [
            {
                "content": [{"type": "text", "text": "You've hit your usage limit for now"}],
                "model": "claude-sonnet-4-6",
                "error": "rate_limit",
            }
        ]
        fresh = QuotaTracker()
        with patch("src.claude_cli.quota_tracker", fresh):
            with pytest.raises(ClaudeResultError) as excinfo:
                cli.parse_claude_message(messages)
        assert excinfo.value.resets_at is None
        window = fresh.snapshot()["windows"]["five_hour"]
        assert window["status"] == "rejected"
        assert window["resets_at"] is None

    def test_assistant_rate_limit_with_generic_text_and_no_reset_is_not_recorded(self):
        """A bare 429 or generic 'rate limited' text with no parsed reset and
        no account-limit wording must not mark five_hour rejected on a guess."""
        from unittest.mock import MagicMock, patch

        from src.claude_cli import ClaudeCodeCLI
        from src.quota_tracker import QuotaTracker

        cli = MagicMock()
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(cli, ClaudeCodeCLI)
        messages = [
            {
                "content": [{"type": "text", "text": "upstream rate limited this request"}],
                "model": "claude-sonnet-4-6",
                "error": "rate_limit",
            }
        ]
        fresh = QuotaTracker()
        with patch("src.claude_cli.quota_tracker", fresh):
            with pytest.raises(ClaudeResultError) as excinfo:
                cli.parse_claude_message(messages)
        assert excinfo.value.resets_at is None
        assert fresh.snapshot()["observed_windows"] == 0


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


class TestQuotaExhaustedResponse:
    def test_session_limit_result_returns_429_with_retry_after(self):
        """The full chain for an exhausted quota: parse_claude_message on the
        SDK's is_error 'success' result must land as 429 + Retry-After, not
        the 502 'SDK returned success' it produced before."""
        import time
        from unittest.mock import MagicMock

        from src.claude_cli import ClaudeCodeCLI

        cli = MagicMock()
        cli.parse_claude_message = ClaudeCodeCLI.parse_claude_message.__get__(cli, ClaudeCodeCLI)
        messages = [
            {
                "subtype": "success",
                "is_error": True,
                "num_turns": 1,
                "errors": [],
                "result": "You've hit your session limit · resets 6pm (UTC)",
            }
        ]
        try:
            cli.parse_claude_message(messages)
            raise AssertionError("expected ClaudeResultError")
        except ClaudeResultError as err:
            resp = _handle_claude_result_error("req-5", "claude-opus-5", err)

        assert resp.status_code == 429
        retry_after = int(resp.headers["Retry-After"])
        assert 1 <= retry_after <= 3600
        body = _body(resp)
        assert body["error"]["code"] == "assistant_rate_limit"
        assert body["error"]["resets_at"] > time.time()

    def test_missing_error_detail_names_the_subtype_without_claiming_success(self):
        err = ClaudeResultError(subtype="success", num_turns=1)
        resp = _build_sdk_error_response("req-6", "claude-opus-5", err)
        assert _body(resp)["error"]["message"] == "SDK returned an error result (subtype=success)"
