"""Tests for plot_chat -- the per-result interpretive follow-up chat.

`_summarize_df_for_chat` is pure pandas -> string, tested directly with no
mocking. `ask_about_result` is tested with a mocked Anthropic client (no
real network call) to confirm it passes the right context through and
returns the mocked response text.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pandas as pd
import pytest

from plot_chat import PlotChatError, _FULL_DATA_ROW_LIMIT, _summarize_df_for_chat, ask_about_result


# ── _summarize_df_for_chat ───────────────────────────────────────────────────

def test_small_df_renders_full_data() -> None:
    df = pd.DataFrame({"month": ["2024-01", "2024-02", "2024-03"], "revenue": [100, 200, 150]})
    summary = _summarize_df_for_chat(df)

    assert "2024-01" in summary
    assert "2024-02" in summary
    assert "2024-03" in summary
    assert "100" in summary and "200" in summary and "150" in summary
    assert "3 row(s) total" in summary


def test_large_df_summarizes_with_explicit_row_count() -> None:
    n = _FULL_DATA_ROW_LIMIT + 25
    df = pd.DataFrame({"category": [f"cat_{i}" for i in range(n)], "value": list(range(n))})
    summary = _summarize_df_for_chat(df)

    # States the true total explicitly rather than silently claiming completeness.
    assert str(n) in summary
    assert "SUMMARY only" in summary
    assert "Do not assume you are seeing every row" in summary

    # Includes head and tail, not the full body -- a middle row should be absent.
    assert "cat_0" in summary
    assert f"cat_{n - 1}" in summary
    assert "cat_30" not in summary  # somewhere in the middle, excluded from head/tail


def test_large_df_does_not_claim_full_result() -> None:
    n = _FULL_DATA_ROW_LIMIT + 1
    df = pd.DataFrame({"x": list(range(n))})
    summary = _summarize_df_for_chat(df)

    assert "Full result" not in summary


def test_boundary_row_count_uses_full_data() -> None:
    df = pd.DataFrame({"x": list(range(_FULL_DATA_ROW_LIMIT))})
    summary = _summarize_df_for_chat(df)

    assert f"{_FULL_DATA_ROW_LIMIT} row(s) total" in summary


# ── ask_about_result ──────────────────────────────────────────────────────────

def _mock_client(reply_text: str) -> MagicMock:
    client = MagicMock()
    text_block = MagicMock()
    text_block.text = reply_text
    client.messages.create.return_value = MagicMock(content=[text_block])
    return client


def test_ask_about_result_returns_mocked_reply_text() -> None:
    client = _mock_client("Looks like a steady upward trend month over month.")
    df = pd.DataFrame({"month": ["2024-01", "2024-02"], "revenue": [100, 200]})
    result_context = {
        "question": "How did revenue trend by month?",
        "sql": "SELECT month, SUM(revenue) AS revenue FROM orders GROUP BY month",
        "chart_spec": {"chart_type": "line", "x": "month", "y": "revenue"},
        "df": df,
    }

    reply = ask_about_result(client, result_context, chat_history=[], question="Any trends?")

    assert reply == "Looks like a steady upward trend month over month."


def test_ask_about_result_passes_context_and_history_into_the_prompt() -> None:
    client = _mock_client("ok")
    df = pd.DataFrame({"category": ["books"], "revenue": [500]})
    result_context = {
        "question": "Which category made the most revenue?",
        "sql": "SELECT category, revenue FROM sales",
        "chart_spec": {"chart_type": "bar"},
        "df": df,
    }
    history = [
        {"role": "user", "content": "Why is books so high?"},
        {"role": "assistant", "content": "It has the most orders."},
    ]

    ask_about_result(client, result_context, chat_history=history, question="Sure about that?")

    _, kwargs = client.messages.create.call_args
    assert result_context["question"] in kwargs["system"]
    assert result_context["sql"] in kwargs["system"]
    assert "books" in kwargs["system"]  # data summary made it into the system prompt

    # History passed in comes first, new user turn appended last -- history
    # itself must not be mutated by the call.
    assert kwargs["messages"] == [*history, {"role": "user", "content": "Sure about that?"}]
    assert history == [
        {"role": "user", "content": "Why is books so high?"},
        {"role": "assistant", "content": "It has the most orders."},
    ]


def test_ask_about_result_raises_plot_chat_error_on_api_error() -> None:
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIError(
        message="boom", request=MagicMock(), body=None
    )
    df = pd.DataFrame({"x": [1]})
    result_context = {"question": "q", "sql": "SELECT 1", "chart_spec": {}, "df": df}

    with pytest.raises(PlotChatError):
        ask_about_result(client, result_context, chat_history=[], question="why?")