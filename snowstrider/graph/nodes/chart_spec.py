"""chart_spec node -- LLM call that proposes a Plotly chart spec for the query result.

Uses `claude-haiku-4-5` with forced tool-use against a small enum-constrained
schema, matching the `self_check` node's pattern -- structured output only,
never free text to parse. The returned dict is consumed by
`charts.render.render_chart`, which independently re-validates every
field against the real result DataFrame before rendering anything.
"""

from __future__ import annotations

import logging
from typing import Callable

import anthropic

from graph.state import SnowstriderState

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512

_TOOL_NAME = "chart_spec"
_TOOL_SCHEMA = {
    "name": _TOOL_NAME,
    "description": "Propose a chart to visualize a SQL query result for the user's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "scatter", "pie", "none"],
                "description": (
                    "'none' if the result doesn't lend itself to a chart "
                    "(e.g. a single scalar value, or too many columns)."
                ),
            },
            "x": {"type": "string", "description": "Column name for the x-axis / category. Empty string if chart_type is 'none'."},
            "y": {"type": "string", "description": "Column name for the y-axis / value. Empty string if chart_type is 'none'."},
            "color": {"type": "string", "description": "Optional column name to color/group by. Empty string if not needed."},
            "agg": {
                "type": "string",
                "enum": ["sum", "avg", "count", "none"],
                "description": "Aggregation to apply to y, if any.",
            },
            "title": {"type": "string", "description": "Short chart title."},
        },
        "required": ["chart_type", "x", "y", "agg", "title"],
    },
}

_SYSTEM_PROMPT = (
    "You are choosing how to visualize a SQL query result for the OLIST e-commerce "
    "dataset. Given the user's question, the executed SQL, and the result's columns/ "
    "inferred dtypes/sample rows, propose the single best chart. Only ever reference "
    "column names that actually appear in result_columns. Call the chart_spec tool "
    "with your proposal."
)

_FALLBACK_SPEC = {"chart_type": "none", "x": "", "y": "", "color": "", "agg": "none", "title": ""}


def make_chart_spec_node(client: anthropic.Anthropic) -> Callable[[SnowstriderState], dict]:
    """Build the `chart_spec` node, closing over the Anthropic client."""

    def chart_spec(state: SnowstriderState) -> dict:
        """Ask Claude Haiku to propose a chart spec for the executed query's result."""
        columns = state.get("result_columns") or []
        preview = state.get("result_preview") or []
        dtypes = _inferred_dtypes(preview, columns)

        user_content = (
            f"Question: {state['question']}\n\n"
            f"SQL executed:\n{state.get('sql_candidate')}\n\n"
            f"Result columns: {columns}\n"
            f"Inferred dtypes: {dtypes}\n"
            f"Result preview (first rows): {preview}\n"
        )

        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": user_content}],
            )
            spec = next(b for b in message.content if b.type == "tool_use").input
        except anthropic.APIError as exc:
            logger.error("chart_spec: Anthropic API call failed: %s", exc)
            return {"chart_spec": dict(_FALLBACK_SPEC)}
        except StopIteration:
            logger.error("chart_spec: response contained no tool_use block")
            return {"chart_spec": dict(_FALLBACK_SPEC)}

        return {"chart_spec": spec}

    return chart_spec


def _inferred_dtypes(preview: list[dict], columns: list[str]) -> dict[str, str]:
    """Cheap python-type inference from the row preview, for prompt context only (not authoritative)."""
    if not preview or not columns:
        return {}
    sample_row = preview[0]
    return {col: type(sample_row.get(col)).__name__ for col in columns if col in sample_row}
