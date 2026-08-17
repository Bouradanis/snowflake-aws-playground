"""Tests for graph.nodes.chart_spec -- chart proposal node.

Mocked Anthropic client (same style as `test_translate_question.py`): no
real network call. Mostly exercises the plain-language title instruction and
the graceful-fallback paths -- the actual chart selection is delegated to
the LLM and re-validated independently by `charts.render.render_chart`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic

from graph.nodes.chart_spec import _SYSTEM_PROMPT, make_chart_spec_node


def _mock_client(spec: dict) -> MagicMock:
    client = MagicMock()
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = spec
    client.messages.create.return_value = MagicMock(content=[tool_use_block])
    return client


def _base_state(**overrides) -> dict:
    state = {
        "question": "monthly revenue trend, YoY",
        "sql_candidate": "SELECT 1",
        "result_columns": ["month", "revenue"],
        "result_preview": [{"month": "2018-01", "revenue": 100.0}],
    }
    state.update(overrides)
    return state


def test_system_prompt_forbids_unexplained_abbreviations() -> None:
    # Regression: chart titles are LLM free text with no built-in structure,
    # so a stakeholder-facing rule against jargon has to live in the prompt.
    assert "YoY" in _SYSTEM_PROMPT
    assert "Year-over-Year" in _SYSTEM_PROMPT
    assert "non-technical" in _SYSTEM_PROMPT


def test_chart_spec_returns_model_proposal() -> None:
    spec = {"chart_type": "line", "x": "month", "y": "revenue", "color": "", "agg": "sum", "title": "Monthly Revenue, Year-over-Year"}
    client = _mock_client(spec)
    node = make_chart_spec_node(client)

    result = node(_base_state())

    assert result["chart_spec"] == spec


def test_chart_spec_falls_back_to_none_on_api_error() -> None:
    client = MagicMock()
    client.messages.create.side_effect = anthropic.APIError(message="boom", request=MagicMock(), body=None)
    node = make_chart_spec_node(client)

    result = node(_base_state())

    assert result["chart_spec"]["chart_type"] == "none"