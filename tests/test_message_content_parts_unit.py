"""Message content parts from agentic clients (tool_use, tool_result, images) must not 422."""

from src.models import Message


def test_text_part_still_normalizes():
    msg = Message(role="user", content=[{"type": "text", "text": "hello"}])
    assert msg.content == "hello"


def test_non_text_parts_are_accepted_and_skipped():
    msg = Message(
        role="assistant",
        content=[
            {"type": "text", "text": "calling"},
            {"type": "tool_use", "id": "t1", "name": "read", "input": {"path": "x"}},
            {"type": "image", "source": {"type": "base64", "data": "AAA"}},
        ],
    )
    assert msg.content == "calling"


def test_tool_result_text_is_kept():
    msg = Message(
        role="user",
        content=[
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": [{"type": "text", "text": "file body"}],
            },
            {"type": "tool_result", "tool_use_id": "t2", "content": "plain"},
        ],
    )
    assert msg.content == "file body\nplain"


def test_null_content_is_tolerated():
    assert Message(role="assistant", content=None).content is None


def test_unknown_part_fields_are_ignored():
    msg = Message(
        role="user",
        content=[{"type": "input_image", "image_url": "data:x"}, {"type": "text", "text": "hi"}],
    )
    assert msg.content == "hi"


def test_non_string_tool_result_text_is_skipped():
    msg = Message(
        role="user",
        content=[{"type": "tool_result", "content": [{"text": 5}, {"text": "ok"}]}],
    )
    assert msg.content == "ok"
