"""self_check node -- cheap plausibility check on the executed query's results.

Uses `claude-haiku-4-5` with forced tool-use (`tool_choice={"type": "tool", ...}`)
against a small `{plausible, reasoning}` schema, so the response is always
structured data rather than free text that would need to be parsed/guessed at.
"""

from __future__ import annotations

import logging
from typing import Callable

import anthropic

from graph.state import SnowstriderState

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512

_TOOL_NAME = "plausibility_verdict"
_TOOL_SCHEMA = {
    "name": _TOOL_NAME,
    "description": (
        "Report whether a SQL query's result plausibly answers the user's original question."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "plausible": {
                "type": "boolean",
                "description": "True if the result plausibly answers the question, False otherwise.",
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences explaining the verdict.",
            },
        },
        "required": ["plausible", "reasoning"],
    },
}

_SYSTEM_PROMPT = (
    "You are reviewing whether a SQL query result plausibly answers a user's question "
    "about the OLIST e-commerce dataset. You are not re-checking SQL syntax and you "
    "cannot re-run the query -- judge only whether the shape of the result (columns, "
    "row count, sample values) makes sense as an answer to the question (e.g. an empty "
    "result for a question that should have matches, or a row count wildly inconsistent "
    "with the question, are red flags). Call the plausibility_verdict tool with your verdict."
)


def make_self_check_node(client: anthropic.Anthropic) -> Callable[[SnowstriderState], dict]:
    """Build the `self_check` node, closing over the Anthropic client."""

    def self_check(state: SnowstriderState) -> dict:
        """Ask Claude Haiku whether the executed query's result plausibly answers the question."""
        user_content = (
            f"Question: {state['question']}\n\n"
            f"SQL executed:\n{state.get('sql_candidate')}\n\n"
            f"Result columns: {state.get('result_columns')}\n"
            f"Result row count: {state.get('result_row_count')}\n"
            f"Result preview (first rows): {state.get('result_preview')}\n"
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
            verdict = next(b for b in message.content if b.type == "tool_use").input
        except anthropic.APIError as exc:
            logger.error("self_check: Anthropic API call failed: %s", exc)
            # Fail toward "needs another look" rather than silently treating
            # an API outage as a passing plausibility check.
            return {
                "self_check_passed": False,
                "self_check_reasoning": f"self-check call failed: {exc}",
            }
        except StopIteration:
            logger.error("self_check: response contained no tool_use block")
            return {
                "self_check_passed": False,
                "self_check_reasoning": "self-check returned no usable verdict",
            }

        return {
            "self_check_passed": bool(verdict.get("plausible")),
            "self_check_reasoning": verdict.get("reasoning", ""),
        }

    return self_check
