#!/usr/bin/env python3
"""
Unit tests for JSON format functionality.

Tests the JSON extraction and enforcement methods in MessageAdapter,
as well as the ResponseFormat model.
"""

import pytest

from src.message_adapter import MessageAdapter
from src.models import ResponseFormat, ChatCompletionRequest, Message


class TestExtractJson:
    """Test MessageAdapter.extract_json() method."""

    def test_extract_json_pure(self):
        """Pure JSON content is returned as-is."""
        content = '{"name": "test", "value": 123}'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_extract_json_pure_array(self):
        """Pure JSON array is returned as-is."""
        content = '[1, 2, 3, 4, 5]'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_extract_json_pure_with_whitespace(self):
        """Pure JSON with surrounding whitespace is extracted."""
        content = '  \n{"key": "value"}\n  '
        result = MessageAdapter.extract_json(content)
        assert result == '{"key": "value"}'

    def test_extract_json_markdown_block(self):
        """Extracts JSON from ```json code block."""
        content = '''Here is the data:
```json
{"items": [1, 2, 3]}
```
That's all!'''
        result = MessageAdapter.extract_json(content)
        assert result == '{"items": [1, 2, 3]}'

    def test_extract_json_generic_code_block(self):
        """Extracts JSON from generic ``` code block."""
        content = '''Response:
```
{"status": "ok"}
```'''
        result = MessageAdapter.extract_json(content)
        assert result == '{"status": "ok"}'

    def test_extract_json_embedded_object(self):
        """Finds JSON object embedded in text."""
        content = 'The result is {"success": true, "count": 42} as expected.'
        result = MessageAdapter.extract_json(content)
        assert result == '{"success": true, "count": 42}'

    def test_extract_json_embedded_array(self):
        """Finds JSON array embedded in text."""
        content = 'Available items: [1, 2, 3] are ready.'
        result = MessageAdapter.extract_json(content)
        assert result == '[1, 2, 3]'

    def test_extract_json_nested_object(self):
        """Extracts nested JSON objects."""
        content = '''Result: {"outer": {"inner": {"deep": "value"}}}'''
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '"deep": "value"' in result

    def test_extract_json_complex_array(self):
        """Extracts complex JSON arrays."""
        content = '''Data: [{"id": 1}, {"id": 2}]'''
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '"id": 1' in result

    def test_extract_json_no_json(self):
        """Returns None when no valid JSON found."""
        content = 'This is just plain text with no JSON.'
        result = MessageAdapter.extract_json(content)
        assert result is None

    def test_extract_json_invalid_json(self):
        """Returns None for malformed JSON."""
        content = '{"broken: json'
        result = MessageAdapter.extract_json(content)
        assert result is None

    def test_extract_json_empty_string(self):
        """Returns None for empty string."""
        result = MessageAdapter.extract_json('')
        assert result is None

    def test_extract_json_none_input(self):
        """Returns None for None input."""
        result = MessageAdapter.extract_json(None)
        assert result is None

    def test_extract_json_prefers_code_block(self):
        """Prefers code block JSON over embedded JSON."""
        content = '''Text {"wrong": "json"}
```json
{"correct": "json"}
```'''
        result = MessageAdapter.extract_json(content)
        assert result == '{"correct": "json"}'

    def test_extract_json_multiline(self):
        """Extracts multiline JSON from code block."""
        content = '''```json
{
    "name": "test",
    "items": [
        1,
        2,
        3
    ]
}
```'''
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '"name": "test"' in result
        assert '"items"' in result


class TestEnforceJsonFormat:
    """Test MessageAdapter.enforce_json_format() method."""

    def test_enforce_json_valid_object(self):
        """Valid JSON object passes through."""
        content = '{"key": "value"}'
        result = MessageAdapter.enforce_json_format(content)
        assert result == content

    def test_enforce_json_valid_array(self):
        """Valid JSON array passes through."""
        content = '[1, 2, 3]'
        result = MessageAdapter.enforce_json_format(content)
        assert result == content

    def test_enforce_json_extracts_from_text(self):
        """Extracts JSON from surrounding text."""
        content = 'Here is the result: {"data": 123}'
        result = MessageAdapter.enforce_json_format(content)
        assert result == '{"data": 123}'

    def test_enforce_json_strict_fallback(self):
        """Returns '[]' on failure in strict mode."""
        content = 'No JSON here at all!'
        result = MessageAdapter.enforce_json_format(content, strict=True)
        assert result == '[]'

    def test_enforce_json_non_strict_returns_original(self):
        """Returns original content on failure in non-strict mode."""
        content = 'No JSON here at all!'
        result = MessageAdapter.enforce_json_format(content, strict=False)
        assert result == content

    def test_enforce_json_from_markdown(self):
        """Extracts JSON from markdown code block."""
        content = '''```json
{"extracted": true}
```'''
        result = MessageAdapter.enforce_json_format(content)
        assert result == '{"extracted": true}'

    def test_enforce_json_empty_strict(self):
        """Empty input returns '[]' in strict mode."""
        result = MessageAdapter.enforce_json_format('', strict=True)
        assert result == '[]'


class TestResponseFormatModel:
    """Test ResponseFormat Pydantic model."""

    def test_response_format_default_text(self):
        """Default type is 'text'."""
        rf = ResponseFormat()
        assert rf.type == "text"

    def test_response_format_text_explicit(self):
        """Can explicitly set type to 'text'."""
        rf = ResponseFormat(type="text")
        assert rf.type == "text"

    def test_response_format_json_object(self):
        """Can set type to 'json_object'."""
        rf = ResponseFormat(type="json_object")
        assert rf.type == "json_object"

    def test_response_format_invalid_type(self):
        """Invalid type raises validation error."""
        with pytest.raises(ValueError):
            ResponseFormat(type="invalid")

    def test_response_format_in_request(self):
        """ResponseFormat can be used in ChatCompletionRequest."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Return JSON")],
            response_format=ResponseFormat(type="json_object"),
        )
        assert request.response_format is not None
        assert request.response_format.type == "json_object"

    def test_response_format_none_in_request(self):
        """ResponseFormat can be None in ChatCompletionRequest."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Hello")],
        )
        assert request.response_format is None

    def test_response_format_dict_input(self):
        """ResponseFormat accepts dict input (OpenAI client style)."""
        request = ChatCompletionRequest(
            messages=[Message(role="user", content="Return JSON")],
            response_format={"type": "json_object"},
        )
        assert request.response_format.type == "json_object"


class TestJsonModeInstruction:
    """Test JSON_MODE_INSTRUCTION constant."""

    def test_json_mode_instruction_exists(self):
        """JSON_MODE_INSTRUCTION constant exists."""
        assert hasattr(MessageAdapter, "JSON_MODE_INSTRUCTION")

    def test_json_mode_instruction_not_empty(self):
        """JSON_MODE_INSTRUCTION is not empty."""
        assert len(MessageAdapter.JSON_MODE_INSTRUCTION) > 0

    def test_json_mode_instruction_mentions_json(self):
        """JSON_MODE_INSTRUCTION mentions JSON."""
        assert "JSON" in MessageAdapter.JSON_MODE_INSTRUCTION.upper()

    def test_json_mode_instruction_is_string(self):
        """JSON_MODE_INSTRUCTION is a string."""
        assert isinstance(MessageAdapter.JSON_MODE_INSTRUCTION, str)


class TestJsonExtractionEdgeCases:
    """Test edge cases for JSON extraction."""

    def test_json_with_escaped_quotes(self):
        """Handles JSON with escaped quotes."""
        content = '{"message": "He said \\"hello\\""}'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_json_with_unicode(self):
        """Handles JSON with unicode characters."""
        content = '{"emoji": "\\u2764", "text": "hello"}'
        result = MessageAdapter.extract_json(content)
        assert result is not None

    def test_json_boolean_values(self):
        """Handles JSON boolean values."""
        content = '{"active": true, "deleted": false}'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_json_null_value(self):
        """Handles JSON null value."""
        content = '{"data": null}'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_json_number_types(self):
        """Handles various JSON number types."""
        content = '{"int": 42, "float": 3.14, "negative": -10, "exp": 1e5}'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_deeply_nested_json(self):
        """Handles deeply nested JSON."""
        content = '{"a": {"b": {"c": {"d": {"e": 1}}}}}'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_json_array_of_objects(self):
        """Handles array of objects."""
        content = '[{"id": 1}, {"id": 2}, {"id": 3}]'
        result = MessageAdapter.extract_json(content)
        assert result == content

    def test_multiple_json_blocks_returns_first_valid(self):
        """When multiple code blocks exist, returns valid JSON from first."""
        content = '''```json
{"first": true}
```
```json
{"second": true}
```'''
        result = MessageAdapter.extract_json(content)
        assert result == '{"first": true}'

    def test_json_with_newlines(self):
        """Handles JSON with embedded newlines."""
        content = '{"text": "line1\\nline2"}'
        result = MessageAdapter.extract_json(content)
        assert result == content
