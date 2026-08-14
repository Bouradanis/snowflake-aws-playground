"""plot_chat -- interpretive follow-up chat about an already-fetched query result.

Distinct from the main "ask a question" flow in `app.py`: this module NEVER
touches the LangGraph graph, never re-runs SQL, and never opens a Snowflake
session. It only ever reasons over data already sitting in memory (the
DataFrame `app.py` retrieves from `graph.nodes.execute_sql.get_result` for
the Raw Data tab) plus the chat thread for that one result, both passed in
by the caller. This module owns no state of its own -- `st.session_state`
(via the per-result `history` entry in `app.py`) is the source of truth for
the conversation thread.
"""

from __future__ import annotations

import logging

import anthropic
import pandas as pd

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# Above this row count, summarize instead of dumping the full DataFrame into
# the prompt -- keeps the prompt bounded and avoids drowning the model in a
# large table it can't usefully reason over anyway.
_FULL_DATA_ROW_LIMIT = 50
_HEAD_ROWS = 10
_TAIL_ROWS = 5

_SYSTEM_PROMPT_TEMPLATE = """You are commenting on the result of a SQL query that has already \
been run against the OLIST e-commerce dataset in Snowflake. You are NOT writing SQL and you \
cannot fetch new data -- you only have what is shown below.

Original question: {question}

SQL that was executed:
{sql}

Chart chosen for this result: {chart_spec}

Data returned (see notes on whether this is the full result or a summary):
{data_summary}

Answer the user's follow-up questions about this result concisely and analytically. If the \
available data can't fully answer a question -- for example a "trend" question when the data \
summary below doesn't show enough of a time dimension, or a "why" question the data itself \
can't explain -- say so plainly rather than fabricating specifics beyond what's shown.
"""


def _summarize_df_for_chat(df: pd.DataFrame) -> str:
    """Render a DataFrame as compact text for an LLM prompt.

    Small results (<= `_FULL_DATA_ROW_LIMIT` rows) are rendered in full as
    CSV text, since the model can reason directly over the real data. Larger
    results are summarized instead (`describe()` stats plus head/tail rows)
    with the true total row count stated explicitly, so the model never
    silently assumes it's looking at the complete result when it isn't.

    Pure function of `df` -- no LLM/network dependency, independently
    unit-testable.
    """
    total_rows = len(df)

    if total_rows <= _FULL_DATA_ROW_LIMIT:
        return (
            f"Full result ({total_rows} row(s) total, all shown below):\n"
            f"{df.to_csv(index=False)}"
        )

    describe_text = df.describe(include="all").to_csv()
    head_text = df.head(_HEAD_ROWS).to_csv(index=False)
    tail_text = df.tail(_TAIL_ROWS).to_csv(index=False)

    return (
        f"This result has {total_rows} rows total -- too many to show in full, so this is a "
        f"SUMMARY only. Do not assume you are seeing every row.\n\n"
        f"Summary statistics (describe):\n{describe_text}\n"
        f"First {_HEAD_ROWS} rows:\n{head_text}\n"
        f"Last {_TAIL_ROWS} rows:\n{tail_text}"
    )


class PlotChatError(Exception):
    """Raised when `ask_about_result` can't get a usable response from the Anthropic API."""


def ask_about_result(
    anthropic_client: anthropic.Anthropic,
    result_context: dict,
    chat_history: list[dict],
    question: str,
) -> str:
    """Answer one interpretive follow-up question about an already-fetched query result.

    Never runs SQL, never touches Snowflake -- `result_context["df"]` is the
    only view of the data this function gets, and it's summarized to text via
    `_summarize_df_for_chat` before ever reaching the model.

    Args:
        anthropic_client: shared client, same one used by the LangGraph nodes.
        result_context: dict with keys `question` (original NL question),
            `sql` (the cleaned SQL that ran), `chart_spec` (dict), and `df`
            (the full result pandas DataFrame).
        chat_history: this result's thread so far, as
            `[{"role": "user"|"assistant", "content": str}, ...]` --
            history *before* the new user turn being asked now.
        question: the new follow-up question to answer.

    Returns:
        The assistant's reply text.

    Raises:
        PlotChatError: if the Anthropic API call fails or returns no usable
            text content.
    """
    data_summary = _summarize_df_for_chat(result_context["df"])
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        question=result_context.get("question"),
        sql=result_context.get("sql"),
        chart_spec=result_context.get("chart_spec"),
        data_summary=data_summary,
    )

    messages = [*chat_history, {"role": "user", "content": question}]

    try:
        message = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        return message.content[0].text.strip()
    except anthropic.APIError as exc:
        logger.error("ask_about_result: Anthropic API call failed: %s", exc)
        raise PlotChatError(f"Could not get a response: {exc}") from exc
    except (IndexError, AttributeError) as exc:
        logger.error("ask_about_result: response contained no usable text content: %s", exc)
        raise PlotChatError("The assistant returned an empty response. Try again.") from exc