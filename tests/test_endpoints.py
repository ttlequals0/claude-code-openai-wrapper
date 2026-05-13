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
