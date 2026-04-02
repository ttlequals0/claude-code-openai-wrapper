"""Tests for function calling simulation."""

import json
import pytest
from src.function_calling import (
    build_tools_system_prompt,
    parse_tool_calls,
    format_tool_calls,
    convert_tool_messages,
)
from src.models import Message, ToolCall, FunctionCall


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
    },
]


class TestBuildToolsSystemPrompt:
    def test_no_tools_returns_empty(self):
        assert build_tools_system_prompt([], None) == ""

    def test_none_choice_returns_empty(self):
        assert build_tools_system_prompt(SAMPLE_TOOLS, "none") == ""

    def test_auto_choice_includes_may_call(self):
        result = build_tools_system_prompt(SAMPLE_TOOLS, "auto")
        assert "MAY call functions" in result
        assert "get_weather" in result
        assert "search" in result

    def test_required_choice_includes_must_call(self):
        result = build_tools_system_prompt(SAMPLE_TOOLS, "required")
        assert "MUST call at least one function" in result

    def test_specific_function_choice(self):
        choice = {"type": "function", "function": {"name": "get_weather"}}
        result = build_tools_system_prompt(SAMPLE_TOOLS, choice)
        assert "MUST call function get_weather" in result

    def test_includes_tool_call_format(self):
        result = build_tools_system_prompt(SAMPLE_TOOLS, "auto")
        assert "```tool_calls" in result

    def test_includes_parameters(self):
        result = build_tools_system_prompt(SAMPLE_TOOLS, "auto")
        assert "location" in result
        assert "query" in result

    def test_default_choice_is_auto(self):
        result = build_tools_system_prompt(SAMPLE_TOOLS)
        assert "MAY call functions" in result


class TestParseToolCalls:
    def test_fenced_tool_calls(self):
        text = 'Some text\n```tool_calls\n[{"name": "get_weather", "arguments": {"location": "NYC"}}]\n```\nMore text'
        calls, remaining = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "get_weather"
        assert calls[0]["arguments"]["location"] == "NYC"
        assert "Some text" in remaining
        assert "More text" in remaining

    def test_multiple_tool_calls(self):
        text = '```tool_calls\n[{"name": "get_weather", "arguments": {"location": "NYC"}}, {"name": "search", "arguments": {"query": "hello"}}]\n```'
        calls, remaining = parse_tool_calls(text)
        assert len(calls) == 2

    def test_bare_json_array_fallback(self):
        text = 'Here are the results:\n[{"name": "search", "arguments": {"query": "test"}}]'
        calls, remaining = parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "search"

    def test_no_tool_calls(self):
        text = "Just a regular response with no function calls."
        calls, remaining = parse_tool_calls(text)
        assert calls == []
        assert remaining == text

    def test_malformed_json_returns_empty(self):
        text = '```tool_calls\nnot valid json\n```'
        calls, remaining = parse_tool_calls(text)
        assert calls == []


class TestFormatToolCalls:
    def test_basic_format(self):
        parsed = [{"name": "get_weather", "arguments": {"location": "NYC"}}]
        result = format_tool_calls(parsed)
        assert len(result) == 1
        assert result[0].type == "function"
        assert result[0].function.name == "get_weather"
        assert result[0].id.startswith("call_")
        assert json.loads(result[0].function.arguments) == {"location": "NYC"}

    def test_multiple_calls_get_unique_ids(self):
        parsed = [
            {"name": "a", "arguments": {}},
            {"name": "b", "arguments": {}},
        ]
        result = format_tool_calls(parsed)
        assert result[0].id != result[1].id


class TestConvertToolMessages:
    def test_assistant_with_tool_calls(self):
        msg = Message(
            role="assistant",
            content="Let me check",
            tool_calls=[
                ToolCall(
                    id="call_123",
                    type="function",
                    function=FunctionCall(name="get_weather", arguments='{"location": "NYC"}'),
                )
            ],
        )
        result = convert_tool_messages([msg])
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert "Called get_weather" in result[0].content
        assert "Let me check" in result[0].content

    def test_tool_result_message(self):
        msg = Message(role="tool", content="72F and sunny", name="get_weather", tool_call_id="call_123")
        result = convert_tool_messages([msg])
        assert len(result) == 1
        assert result[0].role == "user"
        assert "Result of get_weather" in result[0].content

    def test_regular_messages_pass_through(self):
        msg = Message(role="user", content="Hello")
        result = convert_tool_messages([msg])
        assert result[0] is msg

    def test_mixed_conversation(self):
        messages = [
            Message(role="user", content="What's the weather?"),
            Message(
                role="assistant",
                content=None,
                tool_calls=[ToolCall(id="c1", type="function", function=FunctionCall(name="get_weather", arguments='{"location": "NYC"}'))],
            ),
            Message(role="tool", content="72F", name="get_weather", tool_call_id="c1"),
        ]
        result = convert_tool_messages(messages)
        assert len(result) == 3
        assert result[0].role == "user"
        assert result[1].role == "assistant"
        assert result[2].role == "user"
