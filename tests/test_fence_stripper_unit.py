"""Tests for JsonFenceStripper streaming fence removal."""

import pytest
from src.message_adapter import JsonFenceStripper


class TestJsonFenceStripper:
    def test_no_fences(self):
        s = JsonFenceStripper()
        result = s.process_delta('{"key": "value"}')
        result += s.flush()
        assert '"key"' in result
        assert '"value"' in result

    def test_strips_json_fence(self):
        s = JsonFenceStripper()
        chunks = ["```json\n", '{"key": "val', 'ue"}', "\n```"]
        output = ""
        for c in chunks:
            output += s.process_delta(c)
        output += s.flush()
        assert "```" not in output
        assert '"key"' in output

    def test_strips_bare_fence(self):
        s = JsonFenceStripper()
        chunks = ["```\n", '{"a": 1}', "\n```"]
        output = ""
        for c in chunks:
            output += s.process_delta(c)
        output += s.flush()
        assert "```" not in output
        assert '"a"' in output

    def test_no_fence_passes_through(self):
        s = JsonFenceStripper()
        chunks = ['{"hello":', ' "world"}']
        output = ""
        for c in chunks:
            output += s.process_delta(c)
        output += s.flush()
        assert "hello" in output
        assert "world" in output

    def test_empty_chunks(self):
        s = JsonFenceStripper()
        assert s.process_delta("") == ""
        assert s.flush() == ""

    def test_single_large_chunk(self):
        s = JsonFenceStripper()
        text = '```json\n{"data": [1, 2, 3]}\n```'
        output = s.process_delta(text) + s.flush()
        assert "```" not in output
        assert '"data"' in output
