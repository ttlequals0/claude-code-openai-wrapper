#!/usr/bin/env python3
"""
Tests for the Anthropic Messages API compatible endpoint (/v1/messages).

This endpoint provides compatibility with the native Anthropic SDK,
enabling tools like VC to use this wrapper via custom base URL configuration.
"""

import pytest
import requests

from tests.conftest import requires_server

BASE_URL = "http://localhost:8000"


class TestAnthropicMessagesModels:
    """Test Anthropic API model classes."""

    def test_anthropic_text_block(self):
        """Test AnthropicTextBlock model."""
        from src.models import AnthropicTextBlock

        block = AnthropicTextBlock(text="Hello world")
        assert block.type == "text"
        assert block.text == "Hello world"

    def test_anthropic_message(self):
        """Test AnthropicMessage model."""
        from src.models import AnthropicMessage

        # String content
        msg = AnthropicMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

        # List content
        from src.models import AnthropicTextBlock

        msg2 = AnthropicMessage(role="assistant", content=[AnthropicTextBlock(text="Hi there")])
        assert msg2.role == "assistant"
        assert len(msg2.content) == 1

    def test_anthropic_messages_request(self):
        """Test AnthropicMessagesRequest model."""
        from src.models import AnthropicMessagesRequest, AnthropicMessage

        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[AnthropicMessage(role="user", content="Hello")],
            max_tokens=100,
            system="You are helpful",
        )

        assert request.model == "claude-sonnet-4-5-20250929"
        assert len(request.messages) == 1
        assert request.max_tokens == 100
        assert request.system == "You are helpful"

    def test_anthropic_messages_request_to_openai(self):
        """Test conversion from Anthropic to OpenAI message format."""
        from src.models import AnthropicMessagesRequest, AnthropicMessage

        request = AnthropicMessagesRequest(
            model="claude-sonnet-4-5-20250929",
            messages=[
                AnthropicMessage(role="user", content="Hello"),
                AnthropicMessage(role="assistant", content="Hi there"),
                AnthropicMessage(role="user", content="How are you?"),
            ],
        )

        openai_messages = request.to_openai_messages()
        assert len(openai_messages) == 3
        assert openai_messages[0].role == "user"
        assert openai_messages[0].content == "Hello"
        assert openai_messages[1].role == "assistant"
        assert openai_messages[2].content == "How are you?"

    def test_anthropic_messages_response(self):
        """Test AnthropicMessagesResponse model."""
        from src.models import (
            AnthropicMessagesResponse,
            AnthropicTextBlock,
            AnthropicUsage,
        )

        response = AnthropicMessagesResponse(
            model="claude-sonnet-4-5-20250929",
            content=[AnthropicTextBlock(text="Hello!")],
            usage=AnthropicUsage(input_tokens=10, output_tokens=5),
        )

        assert response.type == "message"
        assert response.role == "assistant"
        assert response.model == "claude-sonnet-4-5-20250929"
        assert len(response.content) == 1
        assert response.content[0].text == "Hello!"
        assert response.stop_reason == "end_turn"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5


class TestAnthropicMessagesEndpoint:
    """Integration tests for /v1/messages endpoint."""

    @requires_server
    def test_basic_message(self):
        """Test basic message request."""
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "Say 'test' and nothing else"}],
            },
        )

        assert response.status_code == 200
        result = response.json()

        # Verify Anthropic response format
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert "content" in result
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"
        assert "usage" in result
        assert "input_tokens" in result["usage"]
        assert "output_tokens" in result["usage"]

    @requires_server
    def test_message_with_system_prompt(self):
        """Test message with system prompt."""
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 50,
                "system": "You always respond with exactly one word.",
                "messages": [{"role": "user", "content": "Say hello"}],
            },
        )

        assert response.status_code == 200
        result = response.json()
        assert result["type"] == "message"
        assert len(result["content"]) > 0

    @requires_server
    def test_multi_turn_conversation(self):
        """Test multi-turn conversation."""
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 100,
                "messages": [
                    {"role": "user", "content": "My name is Alice."},
                    {"role": "assistant", "content": "Hello Alice!"},
                    {"role": "user", "content": "What's my name?"},
                ],
            },
        )

        assert response.status_code == 200
        result = response.json()
        assert result["type"] == "message"
        # The response should reference Alice
        response_text = result["content"][0]["text"].lower()
        assert "alice" in response_text

    @requires_server
    def test_invalid_request_missing_messages(self):
        """Test error handling for missing messages."""
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 50,
                # Missing 'messages' field
            },
        )

        assert response.status_code == 422  # Validation error

    @requires_server
    def test_response_format_matches_anthropic_sdk(self):
        """Test that response format matches what Anthropic SDK expects."""
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )

        assert response.status_code == 200
        result = response.json()

        # Required fields for Anthropic SDK compatibility
        assert "id" in result
        assert result["id"].startswith("msg_")
        assert result["type"] == "message"
        assert result["role"] == "assistant"
        assert isinstance(result["content"], list)
        assert result["stop_reason"] in ["end_turn", "max_tokens", "stop_sequence"]
        assert "usage" in result
        assert "input_tokens" in result["usage"]
        assert "output_tokens" in result["usage"]


class TestAnthropicMessagesCliHealthGate:
    """In-process gate check: /v1/messages must return 401 (not 503) when the
    Claude CLI probe failed, so Anthropic SDK clients (VC and similar) route
    the failure as AuthenticationError instead of a transient server error.
    """

    def test_messages_returns_401_when_cli_health_unhealthy(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src import main as main_mod
        from src import auth as auth_mod

        monkeypatch.setattr(auth_mod.auth_manager, "auth_method", "claude_cli", raising=False)
        auth_mod.cli_health.mark_failed("auth_failure", "Not logged in - Please run /login")

        try:
            client = TestClient(main_mod.app)
            resp = client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
        finally:
            auth_mod.cli_health.mark_ok()

        assert resp.status_code == 401, resp.text
        body = resp.json()
        assert body["error"]["type"] == "authentication_error"
        assert body["error"]["code"] == "claude_cli_not_authenticated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
