"""Simulate OpenAI function calling via system prompt injection and response parsing."""

import json
import logging
import re
from uuid import uuid4

from src.models import Message, ToolCall, FunctionCall

logger = logging.getLogger(__name__)

_TOOL_CALL_FORMAT = """IMPORTANT: When you want to call a function, respond with ONLY a code block using the tool_calls language tag:

```tool_calls
[
  {"name": "function_name", "arguments": {"param1": "value1"}}
]
```

You can call multiple functions in one response. Do not include any text outside the code block when calling functions."""


def build_tools_system_prompt(tools: list, tool_choice=None) -> str:
    if not tools and (tool_choice is None or tool_choice == "none"):
        return ""

    if tool_choice == "none":
        return ""

    parts = ["# Available Functions\n"]

    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "unknown")
        description = func.get("description", "No description")
        parameters = func.get("parameters", {})
        parts.append(f"## {name}\n{description}\nParameters: {json.dumps(parameters)}\n")

    if isinstance(tool_choice, dict):
        forced_name = tool_choice.get("function", {}).get("name", "unknown")
        parts.append(f"\nYou MUST call function {forced_name}.\n")
    elif tool_choice == "required":
        parts.append("\nYou MUST call at least one function.\n")
    else:
        parts.append("\nYou MAY call functions if helpful.\n")

    parts.append(_TOOL_CALL_FORMAT)

    return "\n".join(parts)


_INVOKE_RE = re.compile(r'<(?:\w+:)?invoke\s+name="([^"]+)"\s*>(.*?)</(?:\w+:)?invoke>', re.DOTALL)
_PARAM_RE = re.compile(
    r'<(?:\w+:)?parameter\s+name="([^"]+)"\s*>(.*?)</(?:\w+:)?parameter>', re.DOTALL
)
_FUNCTION_CALLS_WRAPPER_RE = re.compile(r"</?(?:\w+:)?function_calls>")


def _parse_param_value(raw: str):
    value = raw.strip()
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def _parse_invoke_blocks(response_text: str, tool_names) -> tuple[list, str]:
    """Parse Claude's native <invoke> markup, for client-defined functions only."""
    calls = []
    spans = []
    for match in _INVOKE_RE.finditer(response_text):
        name = match.group(1)
        if name not in tool_names:
            continue
        arguments = {
            p.group(1): _parse_param_value(p.group(2)) for p in _PARAM_RE.finditer(match.group(2))
        }
        calls.append({"name": name, "arguments": arguments})
        spans.append(match.span())

    if not calls:
        return ([], response_text)

    remaining = response_text
    for start, end in reversed(spans):
        remaining = remaining[:start] + remaining[end:]
    remaining = _FUNCTION_CALLS_WRAPPER_RE.sub("", remaining).strip()
    return (calls, remaining)


def parse_tool_calls(response_text: str, tool_names=None) -> tuple[list, str]:
    # Primary: fenced tool_calls block
    pattern = r"```tool_calls\s*\n(.*?)```"
    match = re.search(pattern, response_text, re.DOTALL)

    if match:
        try:
            calls = json.loads(match.group(1).strip())
            remaining = response_text[: match.start()] + response_text[match.end() :]
            remaining = remaining.strip()
            return (calls, remaining)
        except json.JSONDecodeError:
            logger.warning("Found tool_calls block but failed to parse JSON")

    # Fallback: find [{"name": and try to parse valid JSON from that position
    bare_pattern = r'\[\s*\{\s*"name"\s*:'
    bare_match = re.search(bare_pattern, response_text)

    if bare_match:
        start = bare_match.start()
        # Try increasingly longer substrings to find valid JSON
        for end in range(len(response_text), start, -1):
            if response_text[end - 1] == "]":
                try:
                    calls = json.loads(response_text[start:end])
                    remaining = response_text[:start] + response_text[end:]
                    remaining = remaining.strip()
                    return (calls, remaining)
                except json.JSONDecodeError:
                    continue
        logger.warning("Found bare JSON array marker but failed to parse")

    if tool_names:
        return _parse_invoke_blocks(response_text, set(tool_names))

    return ([], response_text)


def format_tool_calls(parsed_calls: list) -> list:
    result = []
    for call in parsed_calls:
        name = call.get("name", "")
        arguments = call.get("arguments", {})
        result.append(
            ToolCall(
                id=f"call_{uuid4().hex[:24]}",
                type="function",
                function=FunctionCall(
                    name=name,
                    arguments=json.dumps(arguments),
                ),
            )
        )
    return result


def convert_tool_messages(messages: list) -> list:
    converted = []
    for msg in messages:
        # Handle both Message objects and dicts
        if isinstance(msg, Message):
            role = msg.role
            content = msg.content
            tool_calls = msg.tool_calls
            tool_call_id = msg.tool_call_id
            name = msg.name
        else:
            role = msg.get("role", "")
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")
            name = msg.get("name")

        if role == "assistant" and tool_calls:
            parts = []
            if content:
                parts.append(content)
            for tc in tool_calls:
                if hasattr(tc, "function"):
                    fn_name = tc.function.name
                    fn_args = tc.function.arguments
                else:
                    func = tc.get("function", {})
                    fn_name = func.get("name", "unknown")
                    fn_args = func.get("arguments", "{}")
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        pass
                args_str = json.dumps(fn_args) if isinstance(fn_args, dict) else fn_args
                parts.append(f"[Called {fn_name} with arguments: {args_str}]")
            converted.append(Message(role="assistant", content="\n".join(parts)))

        elif role == "tool":
            tid = tool_call_id or "unknown"
            tname = name or "unknown"
            tcontent = content or ""
            converted.append(
                Message(role="user", content=f"[Result of {tname} ({tid}): {tcontent}]")
            )

        else:
            converted.append(msg)

    return converted
