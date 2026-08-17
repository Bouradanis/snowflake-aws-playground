"""Tests for graph.nodes.generate_sql -- SQL candidate generation.

Mocked Anthropic client throughout (same style as `test_plot_chat.py` /
`test_translate_question.py`): no real network call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from graph.nodes.generate_sql import make_generate_sql_node


def _mock_client(reply_text: str) -> MagicMock:
    client = MagicMock()
    text_block = MagicMock()
    text_block.text = reply_text
    client.messages.create.return_value = MagicMock(content=[text_block])
    return client


def _base_state(**overrides) -> dict:
    state = {
        "question": "raw question text",
        "schema_context": "schema context",
        "analytical_brief": None,
        "attempt_count": 0,
    }
    state.update(overrides)
    return state


def test_generate_sql_uses_analytical_brief_when_present() -> None:
    client = _mock_client("SELECT 1")
    node = make_generate_sql_node(client)

    node(_base_state(question="raw question text", analytical_brief="precise SQL-ready brief"))

    _, kwargs = client.messages.create.call_args
    assert kwargs["messages"] == [{"role": "user", "content": "precise SQL-ready brief"}]


def test_generate_sql_falls_back_to_question_when_no_brief() -> None:
    client = _mock_client("SELECT 1")
    node = make_generate_sql_node(client)

    node(_base_state(question="raw question text", analytical_brief=None))

    _, kwargs = client.messages.create.call_args
    assert kwargs["messages"] == [{"role": "user", "content": "raw question text"}]


def test_generate_sql_appends_retry_feedback_after_brief() -> None:
    client = _mock_client("SELECT 1")
    node = make_generate_sql_node(client)

    node(
        _base_state(
            analytical_brief="precise SQL-ready brief",
            attempt_count=1,
            validation_error="bad SQL",
            sql_candidate="SELECT bogus",
        )
    )

    _, kwargs = client.messages.create.call_args
    content = kwargs["messages"][0]["content"]
    assert content.startswith("precise SQL-ready brief")
    assert "bad SQL" in content