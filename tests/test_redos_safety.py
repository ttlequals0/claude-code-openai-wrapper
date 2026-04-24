"""Regression tests for the ReDoS hardening in ``message_adapter.filter_content``.

Each pathological input used to exhibit polynomial backtracking with the
original lazy-``.*?`` regexes that CodeQL's py/polynomial-redos rule flagged
(alerts #3-#6). The rewritten negated-class / bounded patterns are linear,
so each call must complete well under a human-noticeable budget.
"""

from __future__ import annotations

import time

import pytest

from src.message_adapter import MessageAdapter


# Budget in seconds. Linear implementations run these inputs in tens of
# milliseconds; the original lazy patterns would spiral into seconds-to-hours.
REDOS_BUDGET_SECONDS = 1.0


def _time_filter(payload: str) -> float:
    start = time.perf_counter()
    MessageAdapter.filter_content(payload)
    return time.perf_counter() - start


@pytest.mark.parametrize(
    "payload",
    [
        "<thinking>" * 5000 + "x",
        "<attempt_completion>" * 5000 + "x",
        "<attempt_completion>" + ("<result>" * 5000) + "x",
        "[Image:" * 5000,
        "data:image/" * 5000,
        "data:image/png;base64," + ("A" * 20000),
    ],
    ids=[
        "unterminated_thinking",
        "unterminated_attempt_completion",
        "attempt_completion_with_result_storm",
        "image_bracket_storm",
        "data_image_storm",
        "long_base64_trailing",
    ],
)
def test_filter_content_redos_inputs_are_linear(payload: str) -> None:
    elapsed = _time_filter(payload)
    assert elapsed < REDOS_BUDGET_SECONDS, (
        f"filter_content took {elapsed:.3f}s on pathological input; "
        f"expected < {REDOS_BUDGET_SECONDS}s"
    )


def test_filter_content_strips_thinking_block() -> None:
    out = MessageAdapter.filter_content("before<thinking>secret</thinking>after")
    assert "secret" not in out
    assert "before" in out and "after" in out


def test_filter_content_extracts_attempt_completion_inner_result() -> None:
    payload = "<attempt_completion><result>answer</result></attempt_completion>"
    assert MessageAdapter.filter_content(payload) == "answer"


def test_filter_content_replaces_image_tokens() -> None:
    payload = "pre [Image: cat.png] mid data:image/png;base64,ABC post"
    out = MessageAdapter.filter_content(payload)
    assert "[Image: Content not supported by Claude Code]" in out
    assert "ABC" not in out
    assert "pre" in out and "post" in out


def test_filter_content_returns_oversized_input_unchanged() -> None:
    huge = "x" * 2_000_000
    assert MessageAdapter.filter_content(huge) == huge
