"""Tests for graph.nodes.translate_question -- the e-commerce BI specialist node.

Mocked Anthropic client throughout (same style as `test_plot_chat.py`): no
real network call. This node runs once, before `generate_sql`, turning the
user's raw question into a precise SQL-ready analytical brief.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest

from graph.nodes.translate_question import make_translate_question_node


def _mock_client(reply_text: str) -> MagicMock:
    client = MagicMock()
    text_block = MagicMock()
    text_block.text = reply_text
    client.messages.create.return_value = MagicMock(content=[text_block])
    return client


def _base_state(**overrides) -> dict:
    state = {
        "question": "top 10 SKUs by revenue in perfumery for the current MAT, with YA difference",
        "schema_context": "SOME SCHEMA CONTEXT WITH MAT/YTD GLOSSARY",
    }
    state.update(overrides)
    return state


def test_translate_question_returns_analytical_brief_from_model_reply() -> None:
    client = _mock_client("Compute per-product revenue for the perfumery category over the MAT window...")
    node = make_translate_question_node(client)

    result = node(_base_state())

    assert result["analytical_brief"] == (
        "Compute per-product revenue for the perfumery category over the MAT window..."
    )


def test_translate_question_passes_schema_context_into_system_prompt() -> None:
    client = _mock_client("brief")
    node = make_translate_question_node(client)

    node(_base_state(schema_context="UNIQUE_MARKER_XYZ"))

    _, kwargs = client.messages.create.call_args
    assert "UNIQUE_MARKER_XYZ" in kwargs["system"]


def test_translate_question_sends_raw_question_as_user_message() -> None:
    client = _mock_client("brief")
    node = make_translate_question_node(client)

    node(_base_state(question="how many orders shipped last week?"))

    _, kwargs = client.messages.create.call_args
    assert kwargs["messages"] == [{"role": "user", "content": "how many orders shipped last week?"}]


def test_translate_question_falls_back_to_raw_question_on_api_error() -> None:
    # A translation-quality enhancement failing shouldn't fail the whole graph
    # run -- degrade to the pre-existing behavior (generate_sql off the raw
    # question) rather than surfacing a new failure mode to the user.
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIError(message="boom", request=MagicMock(), body=None)
    node = make_translate_question_node(client)

    result = node(_base_state(question="how many orders shipped last week?"))

    assert result["analytical_brief"] == "how many orders shipped last week?"