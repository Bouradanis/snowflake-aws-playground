"""Chat page (SNOW-7 restructure): the original Snowstrider NL-to-SQL question/answer UI.

This is `app.py`'s pre-SNOW-7 page content relocated verbatim into its own
module -- the question form, LangGraph invocation, Chart/Raw Data/SQL Query
result tabs, and the per-result "ask about this result" plot-chat panel
(SNOW-5) are unchanged logic, just moved out of the old single-page
`app.py` so `app.py` can route between this page and the new "Dashboards"
page (`pages_/dashboards.py`) via `st.navigation`.

The SNOW-5 `st.rerun()` fix in `_render_plot_chat` is preserved exactly as
it was -- see the comment at that call site for why it's required.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from charts.render import render_chart
from graph.nodes.execute_sql import get_result
from graph.schema_catalog import format_schema_context
from plot_chat import PlotChatError, ask_about_result

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def _build_initial_state(question: str) -> dict:
    """Build a fresh `SnowstriderState`-shaped dict for one independent question.

    No conversation memory in this slice (SNOW-5) -- every question starts from
    this same blank state regardless of prior questions in `st.session_state["history"]`.
    """
    return {
        "question": question,
        "schema_context": format_schema_context(),
        "sql_candidate": None,
        "validation_error": None,
        "execution_error": None,
        "result_columns": None,
        "result_preview": None,
        "result_row_count": None,
        "self_check_passed": None,
        "self_check_reasoning": None,
        "chart_spec": None,
        "attempt_count": 0,
        "max_attempts": MAX_ATTEMPTS,
        "final_error": None,
        "low_confidence": False,
    }


def _render_result(final_state: dict, entry: dict, key_prefix: str) -> None:
    """Render one final graph state: error banner, or the Chart/Raw Data/SQL Query tabs
    plus the per-result "ask about this result" chat panel.

    `entry` is the `history` dict this result belongs to (holding `question`,
    `final_state`, and this result's `plot_chat` thread) -- needed alongside
    `final_state` so the chat panel can persist its thread on the right entry.
    `key_prefix` gives Streamlit widget keys uniqueness across the "latest
    answer" render and each "previous questions" render in the expander loop,
    since this function is called once per history entry.
    """
    if final_state.get("final_error"):
        st.error(f"Couldn't answer that: {final_state['final_error']}")
        if final_state.get("sql_candidate"):
            st.caption("Last SQL attempted:")
            st.code(final_state["sql_candidate"], language="sql")
        st.caption(f"{final_state.get('attempt_count', 0)} SQL generation attempt(s) made.")
        return

    if final_state.get("low_confidence"):
        st.warning(
            "Self-check never confirmed this result plausibly answers the question. "
            "Showing the data anyway -- review it critically before trusting it."
        )

    # Retrieve the full result DataFrame from execute_sql's in-memory registry
    # instead of re-running the SQL -- re-executing would cost a second
    # warehouse round-trip per question (see graph/nodes/execute_sql.py).
    df = get_result(final_state.get("sql_candidate") or "")

    chart_tab, data_tab, sql_tab = st.tabs(["Chart", "Raw Data", "SQL Query"])

    with chart_tab:
        chart = render_chart(df, final_state.get("chart_spec") or {}) if df is not None else None
        if chart is not None:
            st.plotly_chart(chart, use_container_width=True)
        else:
            st.info("No chart available for this result.")

    with data_tab:
        if df is not None:
            st.dataframe(df, use_container_width=True)
        else:
            st.info(
                "Result data is no longer cached for this query (it aged out of the "
                "in-memory registry) -- ask the question again to re-run it."
            )

    with sql_tab:
        st.code(final_state.get("sql_candidate") or "", language="sql")

    st.caption(f"{final_state.get('attempt_count', 0)} SQL generation attempt(s) made for this question.")

    if df is not None:
        _render_plot_chat(final_state, entry, df, key_prefix)


def _escape_markdown_math(text: str) -> str:
    """Escape `$` so Streamlit's markdown renderer doesn't treat dollar amounts as LaTeX.

    `st.markdown`/`st.write` interpret `$...$` as inline math (KaTeX) by default.
    Plot-chat responses are financial commentary and routinely contain multiple
    dollar figures per message (e.g. "$137K", "$1.17M") -- left unescaped, pairs
    of `$` get parsed as math delimiters and mangle the surrounding text instead
    of rendering it. Escaping preserves the LLM's other markdown (bold, bullets,
    headers) while making `$` display literally.
    """
    return text.replace("$", r"\$")


def _render_plot_chat(final_state: dict, entry: dict, df: pd.DataFrame, key_prefix: str) -> None:
    """Render the "Ask about this result" panel: a per-result chat thread.

    Purely interpretive -- never re-runs SQL, never touches Snowflake, never
    invokes the LangGraph graph. Distinct surface from the "Ask a question
    about the OLIST dataset" form, which always triggers a fresh graph run.
    """
    entry.setdefault("plot_chat", [])
    plot_chat = entry["plot_chat"]

    st.divider()
    st.subheader("Ask about this result")
    st.caption(
        "Ask interpretive questions about the data or chart above (e.g. \"see any trends?\") "
        "-- this does not run new SQL, it only reasons over what's already shown."
    )

    for message in plot_chat:
        with st.chat_message(message["role"]):
            st.write(_escape_markdown_math(message["content"]))

    with st.form(key=f"{key_prefix}_plot_chat_form", clear_on_submit=True):
        follow_up = st.text_input("Ask about this result", label_visibility="collapsed")
        submitted = st.form_submit_button("Send")

    if submitted and follow_up.strip():
        result_context = {
            "question": entry.get("question"),
            "sql": final_state.get("sql_candidate"),
            "chart_spec": final_state.get("chart_spec"),
            "df": df,
        }
        history_before = list(plot_chat)
        plot_chat.append({"role": "user", "content": follow_up.strip()})
        try:
            with st.spinner("Thinking..."):
                reply = ask_about_result(
                    st.session_state["anthropic_client"], result_context, history_before, follow_up.strip()
                )
        except PlotChatError as exc:
            plot_chat.append({"role": "assistant", "content": f"Sorry, something went wrong: {exc}"})
        else:
            plot_chat.append({"role": "assistant", "content": reply})
        # Explicit rerun needed: the `for message in plot_chat` loop that
        # draws the thread runs *before* this form-handling code, earlier in
        # the same script pass, so it already rendered the pre-append state
        # by the time we get here. Without forcing a fresh pass, the new
        # exchange is stored in session_state but stays invisible until some
        # later, unrelated interaction triggers the next rerun (confirmed
        # live -- SNOW-5 bug report: single Enter/click appended the message
        # but showed nothing until an extra submission).
        st.rerun()

    if plot_chat:
        st.caption(f"{len(plot_chat)} follow-up message(s) about this result.")


def render_page() -> None:
    """Render the Chat page: question form, latest result, and session scrollback.

    Assumes `st.session_state["graph"]`/`["history"]` are already populated by
    `app.py`'s login flow -- this page is only reachable once logged in.
    """
    st.title(":snowflake: Snowstrider")
    st.caption("Natural-language questions over OLIST.RAW, via LangGraph and your own Anthropic key.")

    with st.form("question_form"):
        question = st.text_input("Ask a question about the OLIST dataset")
        ask = st.form_submit_button("Ask")

    if ask and question.strip():
        graph = st.session_state["graph"]
        initial_state = _build_initial_state(question.strip())
        try:
            with st.spinner("Thinking..."):
                final_state = graph.invoke(initial_state)
        except Exception as exc:  # noqa: BLE001 -- graph nodes already catch their own API/SQL
            # errors internally; this is a last-resort guard against anything that slips through.
            logger.exception("chat: unhandled error invoking the graph")
            st.error(f"Something went wrong answering that question: {exc}")
        else:
            st.session_state["history"].append({"question": question.strip(), "final_state": final_state})

    history = st.session_state["history"]
    if history:
        st.divider()
        st.subheader("Latest answer")
        latest = history[-1]
        st.markdown(f"**Q:** {latest['question']}")
        _render_result(latest["final_state"], latest, key_prefix=f"latest_{len(history) - 1}")

        if len(history) > 1:
            with st.expander(f"Previous questions this session ({len(history) - 1})"):
                for idx, entry in reversed(list(enumerate(history[:-1]))):
                    st.markdown(f"**Q:** {entry['question']}")
                    _render_result(entry["final_state"], entry, key_prefix=f"prev_{idx}")
                    st.divider()
