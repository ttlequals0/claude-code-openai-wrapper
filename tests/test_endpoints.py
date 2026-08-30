#!/usr/bin/env python3
"""
Quick endpoint test for Claude Code OpenAI wrapper.
Run this while the server is running on localhost:8000
"""

import pytest
import requests

from tests.conftest import requires_server
import json

BASE_URL = "http://localhost:8000"


@requires_server
def test_health():
    print("Testing /health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False


@requires_server
def test_auth_status():
    print("\nTesting /v1/auth/status endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/v1/auth/status")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False


@requires_server
def test_models():
    print("\nTesting /v1/models endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/v1/models")
        print(f"  Status: {response.status_code}")
        models = response.json()
        print(f"  Found {len(models.get('data', []))} models")
        for model in models.get("data", [])[:3]:  # Show first 3
            print(f"    - {model.get('id')}")
        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False


@requires_server
def test_chat_completion():
    print("\nTesting /v1/chat/completions endpoint...")
    try:
        payload = {
            "model": "claude-3-5-haiku-20241022",  # Use fastest model
            "messages": [
                {
                    "role": "user",
                    "content": "Say 'Hello, SDK integration working!' and nothing else.",
                }
            ],
            "max_tokens": 50,
        }

        response = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  Response: {content}")
            print(f"  Usage: {result.get('usage', {})}")
            return True
        else:
            print(f"  Error: {response.text}")
            return False

    except Exception as e:
        print(f"  Error: {e}")
        return False


def main():
    print("Claude Code OpenAI Wrapper - Endpoint Tests")
    print("=" * 50)

    tests = [
        ("Health Check", test_health),
        ("Auth Status", test_auth_status),
        ("Models List", test_models),
        ("Chat Completion", test_chat_completion),
    ]

    passed = 0
    total = len(tests)

    for name, test_func in tests:
        if test_func():
            print(f"✓ {name} passed")
            passed += 1
        else:
            print(f"✗ {name} failed")

    print("=" * 50)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! SDK integration is working correctly.")
    else:
        print("❌ Some tests failed. Check server logs for details.")


if __name__ == "__main__":
    main()


class TestChatCompletionsCliHealthGate:
    """In-process gate check: when auth_method=claude_cli and the latest probe
    failed, /v1/chat/completions must return 401 with an OpenAI-shaped
    authentication_error body, without touching the SDK.
    """

    def test_chat_completions_returns_401_when_cli_health_unhealthy(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src import main as main_mod
        from src import auth as auth_mod

        monkeypatch.setattr(auth_mod.auth_manager, "auth_method", "claude_cli", raising=False)
        auth_mod.cli_health.mark_failed("auth_failure", "Not logged in - Please run /login")

        try:
            client = TestClient(main_mod.app)
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "claude-sonnet-4-6",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        finally:
            auth_mod.cli_health.mark_ok()

        assert resp.status_code == 401, resp.text
        body = resp.json()
        assert body["error"]["type"] == "authentication_error"
        assert body["error"]["code"] == "claude_cli_not_authenticated"
        assert body["error"]["error_kind"] == "auth_failure"

    @pytest.mark.parametrize("kind", ["quota_exhausted", "unknown"])
    def test_non_auth_probe_failure_does_not_gate_with_401(self, monkeypatch, kind):
        """Regression for the 2026-08-30 outage.

        A quota rejection was classified 'unknown' - explicitly not an auth
        problem - yet the gate keyed on `ok` alone and returned 401 for 13.5
        hours. Only 'auth_failure' may produce 401.

        Checks the gate directly: letting it fall through in-process would
        issue a real SDK call.
        """
        from src import main as main_mod
        from src import auth as auth_mod

        monkeypatch.setattr(auth_mod.auth_manager, "auth_method", "claude_cli", raising=False)
        monkeypatch.setattr(main_mod, "validate_claude_code_auth", lambda: (True, {}))
        auth_mod.cli_health.mark_failed(kind, "Claude Code returned an error result: success")

        try:
            assert main_mod._check_cli_auth_or_401() is None
        finally:
            auth_mod.cli_health.mark_ok()

    def test_auth_failure_still_gates_with_401(self, monkeypatch):
        from src import main as main_mod
        from src import auth as auth_mod

        monkeypatch.setattr(auth_mod.auth_manager, "auth_method", "claude_cli", raising=False)
        auth_mod.cli_health.mark_failed("auth_failure", "Not logged in")

        try:
            blocked = main_mod._check_cli_auth_or_401()
        finally:
            auth_mod.cli_health.mark_ok()

        assert blocked is not None
        assert blocked.status_code == 401


class TestUsageEndpoint:
    """GET /v1/usage reports the quota state the CLI last told us about."""

    def test_reports_recorded_windows(self):
        import time

        from fastapi.testclient import TestClient

        from src import main as main_mod
        from src.quota_tracker import QuotaTracker

        original = main_mod.quota_tracker
        tracker = QuotaTracker()
        reset = int(time.time()) + 1200
        tracker.record(
            {
                "status": "allowed_warning",
                "resets_at": reset,
                "rate_limit_type": "five_hour",
                "utilization": 0.93,
            }
        )
        main_mod.quota_tracker = tracker
        try:
            resp = TestClient(main_mod.app).get("/v1/usage")
        finally:
            main_mod.quota_tracker = original

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["blocked"] is False
        assert body["windows"]["five_hour"]["utilization"] == 0.93
        assert body["windows"]["five_hour"]["resets_at"] == reset

    def test_idle_wrapper_reports_no_windows(self):
        from fastapi.testclient import TestClient

        from src import main as main_mod
        from src.quota_tracker import QuotaTracker

        original = main_mod.quota_tracker
        main_mod.quota_tracker = QuotaTracker()
        try:
            resp = TestClient(main_mod.app).get("/v1/usage")
        finally:
            main_mod.quota_tracker = original

        assert resp.status_code == 200, resp.text
        assert resp.json()["observed_windows"] == 0


class TestQuotaEnforcementGate:
    """_check_quota_or_429 is opt-in and only fires on a live rejection."""

    @staticmethod
    def _blocked_tracker():
        import time

        from src.quota_tracker import QuotaTracker

        tracker = QuotaTracker()
        tracker.record(
            {
                "status": "rejected",
                "resets_at": int(time.time()) + 1800,
                "rate_limit_type": "five_hour",
            }
        )
        return tracker

    def test_disabled_by_default(self, monkeypatch):
        from src import main as main_mod

        monkeypatch.delenv("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", raising=False)
        monkeypatch.setattr(main_mod, "quota_tracker", self._blocked_tracker())
        assert main_mod._check_quota_or_429() is None

    def test_blocks_with_429_and_reset_when_enabled(self, monkeypatch):
        from src import main as main_mod

        monkeypatch.setenv("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", "true")
        monkeypatch.setattr(main_mod, "quota_tracker", self._blocked_tracker())

        blocked = main_mod._check_quota_or_429()
        assert blocked is not None
        assert blocked.status_code == 429
        body = json.loads(blocked.body)["error"]
        assert body["code"] == "upstream_quota_exhausted"
        assert body["type"] == "rate_limit_exceeded"
        assert body["seconds_until_reset"] > 0
        assert int(blocked.headers["retry-after"]) > 0

    def test_passes_when_quota_is_healthy(self, monkeypatch):
        from src import main as main_mod
        from src.quota_tracker import QuotaTracker

        monkeypatch.setenv("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", "true")
        tracker = QuotaTracker()
        tracker.record({"status": "allowed", "rate_limit_type": "five_hour"})
        monkeypatch.setattr(main_mod, "quota_tracker", tracker)
        assert main_mod._check_quota_or_429() is None

    def test_counts_requests_even_when_disabled(self, monkeypatch):
        """Probe cadence must not depend on enforcement being on."""
        from src import main as main_mod
        from src.quota_tracker import QuotaTracker

        monkeypatch.delenv("WRAPPER_QUOTA_ENFORCEMENT_ENABLED", raising=False)
        tracker = QuotaTracker()
        monkeypatch.setattr(main_mod, "quota_tracker", tracker)

        for _ in range(3):
            main_mod._check_quota_or_429()
        assert tracker.probe_due(3) is True
