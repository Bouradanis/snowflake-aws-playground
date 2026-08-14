"""Snowstrider -- standalone Streamlit front end for the OLIST NL-to-SQL LangGraph pipeline.

Snowflake Cortex Analyst is blocked on this trial account, and Streamlit-in-
Snowflake's Container Runtime (needed for real `langgraph`/`sqlglot`) is
blocked too -- trial accounts can't create the External Access Integration
it requires (see CLAUDE.md, "Front end -- resolved (SNOW-4)"). So this app
runs standalone (locally, or on Streamlit Community Cloud) and opens its own
per-session Snowpark `Session` from credentials entered in the login form
below -- that login *is* the app's entire auth mechanism, reusing Snowflake's
own login rather than building anything custom.

This module only wires Streamlit widgets to the already-built/tested backend
(`graph.build_graph`, `graph.nodes.execute_sql.get_result`,
`charts.render.render_chart`, `snowflake_conn`) -- it does not
reimplement any graph/validation/chart logic.
"""

from __future__ import annotations

import logging

import streamlit as st
from snowflake.snowpark.exceptions import SnowparkSQLException

from charts.render import render_chart
from graph.build_graph import build_graph
from graph.nodes.execute_sql import get_result
from graph.schema_catalog import format_schema_context

from snowflake_conn import get_anthropic_client, get_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Snowstrider", page_icon=":snowflake:", layout="wide")

MAX_ATTEMPTS = 3


def _init_session_state() -> None:
    """Set default `st.session_state` keys on first run. Idempotent across reruns."""
    st.session_state.setdefault("snowflake_session", None)
    st.session_state.setdefault("anthropic_client", None)
    st.session_state.setdefault("graph", None)
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("login_error", None)


def _is_logged_in() -> bool:
    """A session is considered logged in once a live Snowpark `Session` is cached."""
    return st.session_state.get("snowflake_session") is not None


def _handle_login(account: str, user: str, password: str) -> None:
    """Open a Snowpark session, build the Anthropic client, and compile the graph -- once.

    On any failure, sets `st.session_state["login_error"]` to a clean, actionable
    message (never a raw stack trace) and leaves the session unauthenticated so the
    user can retry without restarting the app. The `password` argument is used only
    to build the connection and is never logged, printed, or stored anywhere.
    """
    try:
        session = get_session(account=account, user=user, password=password)
    except ValueError as exc:
        st.session_state["login_error"] = str(exc)
        return
    except SnowparkSQLException as exc:
        logger.error("login: Snowflake rejected the connection attempt for user=%s", user)
        st.session_state["login_error"] = (
            "Snowflake rejected that login. Check your account identifier, username, "
            "and password and try again."
        )
        return
    except Exception:  # noqa: BLE001 -- last-resort guard so a raw stack trace never reaches the UI
        logger.exception("login: unexpected error opening Snowflake session")
        st.session_state["login_error"] = (
            "Could not connect to Snowflake. Check your account identifier and network, "
            "then try again."
        )
        return

    try:
        anthropic_client = get_anthropic_client()
    except RuntimeError as exc:
        session.close()
        st.session_state["login_error"] = str(exc)
        return

    st.session_state["snowflake_session"] = session
    st.session_state["anthropic_client"] = anthropic_client
    st.session_state["graph"] = build_graph(session, anthropic_client)
    st.session_state["login_error"] = None
    logger.info("login: Snowflake session and graph established for user=%s", user)


def _logout() -> None:
    """Close the Snowpark session (never just drop it) and clear all session state."""
    session = st.session_state.get("snowflake_session")
    if session is not None:
        try:
            session.close()
        except Exception:  # noqa: BLE001 -- best-effort cleanup, never block logout on this
            logger.exception("logout: error closing Snowpark session")
    st.session_state.clear()


def _render_login_form() -> None:
    """Render the login gate: Snowflake account / username / password."""
    st.title(":snowflake: Snowstrider")
    st.write(
        "Ask natural-language questions over the OLIST e-commerce dataset in Snowflake. "
        "Log in with your own Snowflake account to get started -- this app does not store "
        "or share your credentials, and opens a fresh session for you alone."
    )

    with st.form("login_form"):
        account = st.text_input("Snowflake account identifier", placeholder="e.g. xy12345.us-east-1")
        user = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        with st.spinner("Connecting to Snowflake..."):
            _handle_login(account.strip(), user.strip(), password)
        if st.session_state.get("snowflake_session") is not None:
            st.rerun()

    if st.session_state.get("login_error"):
        st.error(st.session_state["login_error"])


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


def _render_result(final_state: dict) -> None:
    """Render one final graph state: error banner, or the Chart/Raw Data/SQL Query tabs."""
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


def _render_app() -> None:
    """Render the logged-in app: question form, latest result, and session scrollback."""
    st.title(":snowflake: Snowstrider")
    st.caption("Natural-language questions over OLIST.RAW, via LangGraph and your own Anthropic key.")

    with st.sidebar:
        st.button("Log out", on_click=_logout)

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
            logger.exception("app: unhandled error invoking the graph")
            st.error(f"Something went wrong answering that question: {exc}")
        else:
            st.session_state["history"].append({"question": question.strip(), "final_state": final_state})

    history = st.session_state["history"]
    if history:
        st.divider()
        st.subheader("Latest answer")
        latest = history[-1]
        st.markdown(f"**Q:** {latest['question']}")
        _render_result(latest["final_state"])

        if len(history) > 1:
            with st.expander(f"Previous questions this session ({len(history) - 1})"):
                for entry in reversed(history[:-1]):
                    st.markdown(f"**Q:** {entry['question']}")
                    _render_result(entry["final_state"])
                    st.divider()


def main() -> None:
    """Entry point: login gate first, then the question/answer app once authenticated."""
    _init_session_state()
    if _is_logged_in():
        _render_app()
    else:
        _render_login_form()


if __name__ == "__main__":
    main()
