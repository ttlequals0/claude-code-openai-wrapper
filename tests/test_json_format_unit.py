#!/usr/bin/env python3
"""
Unit tests for JSON format functionality.

Tests the JSON extraction and enforcement methods in MessageAdapter,
as well as the ResponseFormat model.
"""

import pytest

from src.message_adapter import MessageAdapter, JsonExtractionResult
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


class TestBalancedJsonExtraction:
    """Test the balanced brace/bracket matching algorithm."""

    def test_deeply_nested_objects(self):
        """Handles deeply nested objects with balanced matching."""
        content = 'Preamble: {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}'
        result = MessageAdapter.extract_json(content)
        assert result == '{"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}'

    def test_mixed_nesting(self):
        """Handles mixed objects and arrays."""
        content = 'Result: {"items": [{"id": 1, "nested": {"value": [1,2,3]}}]}'
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '"items"' in result
        assert '"nested"' in result

    def test_escaped_quotes_in_strings(self):
        """Handles escaped quotes within strings."""
        content = '''{"message": "He said \\"hello\\" to me", "count": 1}'''
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '\\"hello\\"' in result

    def test_braces_inside_strings(self):
        """Ignores braces inside string values."""
        content = '{"code": "function() { return {}; }", "valid": true}'
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '"valid": true' in result

    def test_brackets_inside_strings(self):
        """Ignores brackets inside string values."""
        content = '{"regex": "[a-z]+", "array": [1, 2, 3]}'
        result = MessageAdapter.extract_json(content)
        assert result is not None
        assert '"array": [1, 2, 3]' in result

    def test_preamble_stripping(self):
        """Removes common Claude preambles before JSON."""
        content = "Here's the JSON: {\"key\": \"value\"}"
        result = MessageAdapter.extract_json(content)
        assert result == '{"key": "value"}'

    def test_heres_the_response_preamble(self):
        """Handles 'Here is the response:' preamble."""
        content = "Here is the response: {\"status\": \"ok\"}"
        result = MessageAdapter.extract_json(content)
        assert result == '{"status": "ok"}'

    def test_result_preamble(self):
        """Handles 'Result:' preamble."""
        content = "Result: [1, 2, 3, 4, 5]"
        result = MessageAdapter.extract_json(content)
        assert result == '[1, 2, 3, 4, 5]'


class TestJsonExtractionMetadata:
    """Test the extract_json_with_metadata method."""

    def test_direct_extraction_method(self):
        """Reports 'direct' method for pure JSON."""
        content = '{"pure": "json"}'
        result = MessageAdapter.extract_json_with_metadata(content)
        assert result.success is True
        assert result.method == "direct"
        assert result.content == content

    def test_preamble_removed_method(self):
        """Reports 'preamble_removed' method when preamble stripped."""
        content = "Here's the JSON: {\"key\": \"value\"}"
        result = MessageAdapter.extract_json_with_metadata(content)
        assert result.success is True
        assert result.method == "preamble_removed"
        assert result.preamble_found == "Here's the JSON:"

    def test_code_block_method(self):
        """Reports 'code_block' method for markdown extraction."""
        content = '''```json
{"extracted": true}
```'''
        result = MessageAdapter.extract_json_with_metadata(content)
        assert result.success is True
        assert result.method == "code_block"

    def test_brace_match_method(self):
        """Reports 'brace_match' for balanced extraction."""
        content = 'Some text {"embedded": true} more text'
        result = MessageAdapter.extract_json_with_metadata(content)
        assert result.success is True
        assert result.method == "brace_match"

    def test_length_tracking(self):
        """Tracks original and extracted lengths."""
        content = '   {"padded": true}   '
        result = MessageAdapter.extract_json_with_metadata(content)
        assert result.original_length == len(content)
        assert result.extracted_length == len('{"padded": true}')

    def test_failure_reporting(self):
        """Reports failure correctly for invalid content."""
        content = 'No JSON here at all!'
        result = MessageAdapter.extract_json_with_metadata(content)
        assert result.success is False
        assert result.method == "failed"
        assert result.content is None

    def test_empty_content(self):
        """Handles empty content."""
        result = MessageAdapter.extract_json_with_metadata("")
        assert result.success is False
        assert result.method == "failed"
        assert result.original_length == 0


class TestEnforceJsonFormatWithMetadata:
    """Test enforce_json_format_with_metadata method."""

    def test_returns_tuple(self):
        """Returns tuple of (content, metadata)."""
        content = '{"key": "value"}'
        result = MessageAdapter.enforce_json_format_with_metadata(content)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_metadata_dict_structure(self):
        """Metadata dict contains expected keys."""
        content = '{"key": "value"}'
        json_content, metadata = MessageAdapter.enforce_json_format_with_metadata(content)
        assert "success" in metadata
        assert "method" in metadata
        assert "original_length" in metadata
        assert "extracted_length" in metadata
        assert "strict_mode" in metadata

    def test_strict_mode_in_metadata(self):
        """Strict mode is reflected in metadata."""
        content = 'No JSON'
        _, metadata_strict = MessageAdapter.enforce_json_format_with_metadata(content, strict=True)
        _, metadata_non_strict = MessageAdapter.enforce_json_format_with_metadata(content, strict=False)

        assert metadata_strict["strict_mode"] is True
        assert metadata_non_strict["strict_mode"] is False

    def test_fallback_used_on_failure(self):
        """Reports fallback_used when extraction fails."""
        content = 'No JSON here!'
        _, metadata = MessageAdapter.enforce_json_format_with_metadata(content, strict=True)
        assert metadata.get("fallback_used") is True
        assert metadata.get("fallback_value") == "[]"

    def test_preamble_in_metadata(self):
        """Preamble is included in metadata when found."""
        content = "Here's the JSON: {\"key\": \"value\"}"
        _, metadata = MessageAdapter.enforce_json_format_with_metadata(content)
        assert metadata.get("preamble_found") == "Here's the JSON:"


class TestCommonPreambles:
    """Test COMMON_PREAMBLES constant."""

    def test_common_preambles_exists(self):
        """COMMON_PREAMBLES constant exists."""
        assert hasattr(MessageAdapter, "COMMON_PREAMBLES")

    def test_common_preambles_is_list(self):
        """COMMON_PREAMBLES is a list."""
        assert isinstance(MessageAdapter.COMMON_PREAMBLES, list)

    def test_common_preambles_not_empty(self):
        """COMMON_PREAMBLES is not empty."""
        assert len(MessageAdapter.COMMON_PREAMBLES) > 0

    def test_common_preambles_includes_heres(self):
        """COMMON_PREAMBLES includes 'Here's the JSON:' variant."""
        preambles_lower = [p.lower() for p in MessageAdapter.COMMON_PREAMBLES]
        assert any("here's the json" in p for p in preambles_lower)

    def test_common_preambles_includes_here_is(self):
        """COMMON_PREAMBLES includes 'Here is the JSON:' variant."""
        preambles_lower = [p.lower() for p in MessageAdapter.COMMON_PREAMBLES]
        assert any("here is the json" in p for p in preambles_lower)
