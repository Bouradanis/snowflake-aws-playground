"""generate_sql node -- turns a question (plus retry feedback, if any) into SQL text.

Read-only reference: `oci-ai-playground/olist_copilot/app.py`'s `generate_sql()`
uses the same model family (`claude-sonnet-4-6`) and a single-shot
system-prompt-as-schema-context pattern. This node deliberately goes further
than that one-shot approach: it's one step in a langgraph retry loop that
feeds back the previous attempt's validation/execution/plausibility failure
so the model can self-correct, rather than a single ungraded attempt.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import anthropic

from graph.state import SnowstriderState

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

_SYSTEM_PROMPT_TEMPLATE = """You are a Snowflake SQL expert generating a single read-only query \
against the OLIST.RAW schema.

{schema_context}

Snowflake SQL rules -- follow these exactly:
- Only ever write a single SELECT statement (a WITH/CTE prefix is fine, but the \
statement must still resolve to one SELECT). Never write INSERT/UPDATE/DELETE/\
CREATE/DROP/ALTER/MERGE/CALL/COPY INTO/EXECUTE IMMEDIATE or any other DML/DDL/\
admin command.
- Only reference the OLIST.RAW tables and columns listed above. Do not invent \
tables or columns.
- Use LIMIT n (Snowflake also accepts FETCH FIRST n ROWS ONLY, but prefer LIMIT).
- Use DATE_TRUNC('MONTH', col) or TO_CHAR(col, 'YYYY-MM') for month grouping.
- Return ONLY the raw SQL text. No markdown code fences, no explanation, no \
commentary before or after the query.
"""


def make_generate_sql_node(client: anthropic.Anthropic) -> Callable[[SnowstriderState], dict]:
    """Build the `generate_sql` node, closing over the Anthropic client.

    The Snowpark session and Anthropic client are bound into node closures at
    graph-build time (see `graph/build_graph.py`) rather than re-created per
    call, since langgraph node functions only ever receive `state`.
    """

    def generate_sql(state: SnowstriderState) -> dict:
        """Call Claude to produce a SQL candidate; increments `attempt_count`."""
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(schema_context=state["schema_context"])

        # Prefer the `translate_question` node's analytical brief -- a
        # precise, SQL-ready restatement of the question with every business
        # term (MAT/YTD/YA/etc.) resolved and every part of a compound ask
        # spelled out -- over the raw question. Falls back to the raw
        # question if translation is unavailable (e.g. its own API call
        # failed and it degraded to passing the question through unchanged,
        # or this node is exercised directly without that node having run).
        base_content = state.get("analytical_brief") or state["question"]
        user_content = base_content
        feedback = _retry_feedback(state)
        if feedback:
            user_content = f"{base_content}\n\n{feedback}"

        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            sql_text = _strip_markdown_fences(message.content[0].text.strip())
        except anthropic.APIError as exc:
            logger.error("generate_sql: Anthropic API call failed: %s", exc)
            # Treat an API failure as a failed attempt (surfaced via
            # validation_error) so the existing retry/give_up routing handles
            # it the same way as a bad query, instead of needing a separate
            # error path.
            return {
                "sql_candidate": None,
                "validation_error": f"SQL generation failed: {exc}",
                "attempt_count": state["attempt_count"] + 1,
            }

        logger.info("generate_sql: produced candidate on attempt %d", state["attempt_count"] + 1)
        return {
            "sql_candidate": sql_text,
            "attempt_count": state["attempt_count"] + 1,
        }

    return generate_sql


def _retry_feedback(state: SnowstriderState) -> Optional[str]:
    """Build a feedback string for the retry prompt from the most recent failure, if any."""
    if state.get("attempt_count", 0) <= 0:
        return None

    if state.get("validation_error"):
        return (
            f"Your previous SQL failed validation with: {state['validation_error']}\n"
            f"Previous SQL:\n{state.get('sql_candidate') or ''}\n"
            "Fix the query and try again."
        )
    if state.get("execution_error"):
        return (
            f"Your previous SQL failed to execute against Snowflake with: {state['execution_error']}\n"
            f"Previous SQL:\n{state.get('sql_candidate') or ''}\n"
            "Fix the query and try again."
        )
    if state.get("self_check_passed") is False and state.get("self_check_reasoning"):
        return (
            "Your previous SQL ran successfully, but its results were judged implausible "
            f"for the question: {state['self_check_reasoning']}\n"
            f"Previous SQL:\n{state.get('sql_candidate') or ''}\n"
            "Reconsider the query and try again."
        )
    return None


def _strip_markdown_fences(text: str) -> str:
    """Strip a ```sql ... ``` or ``` ... ``` wrapper if the model added one despite instructions."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]  # drop opening fence (with optional language tag)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped
