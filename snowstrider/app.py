"""Snowstrider -- standalone Streamlit front end for the OLIST NL-to-SQL LangGraph pipeline.

Snowflake Cortex Analyst is blocked on this trial account, and Streamlit-in-
Snowflake's Container Runtime (needed for real `langgraph`/`sqlglot`) is
blocked too -- trial accounts can't create the External Access Integration
it requires (see CLAUDE.md, "Front end -- resolved (SNOW-4)"). So this app
runs standalone (locally, or on Streamlit Community Cloud) and opens its own
per-session Snowpark `Session` from credentials entered in the login form
below -- that login *is* the app's entire auth mechanism, reusing Snowflake's
own login rather than building anything custom.

This module is now a thin entrypoint (SNOW-7 restructure): the login gate
lives here (unchanged from before), and once logged in it hands off to
`st.navigation` to route between the "Chat" page (`pages_/chat.py` -- the
original NL-to-SQL question/answer UI, moved not rewritten) and the new
"Dashboards" page (`pages_/dashboards.py`, SNOW-7's deterministic e-commerce
KPI dashboard). `st.session_state` (`snowflake_session`, `anthropic_client`,
`graph`, `history`) is set up here and shared across both pages, same as it
was implicitly shared across reruns of the single-page app before this split.
"""

from __future__ import annotations

import logging

import streamlit as st
from snowflake.snowpark.exceptions import SnowparkSQLException

from graph.build_graph import build_graph
from pages_ import chat, dashboards
from snowflake_conn import get_anthropic_client, get_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Snowstrider", page_icon=":snowflake:", layout="wide")


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


def _render_app() -> None:
    """Render the logged-in app: shared sidebar (log out) + page navigation.

    "Log out" is rendered here, outside either page, so it's available no
    matter which page (Chat or Dashboards) is currently selected -- in the
    pre-SNOW-7 single-page app it lived inside the page body, which was fine
    with only one page but would strand the user on Dashboards with no way
    back out without this move.
    """
    with st.sidebar:
        st.button("Log out", on_click=_logout)

    # `url_path` is set explicitly on both -- without it, Streamlit infers the
    # URL pathname from the page callable's `__name__`, and both page modules
    # expose a `render_page` function by convention, which collided
    # ("Multiple Pages specified with URL pathname render_page") and crashed
    # `st.navigation` at runtime. Confirmed live via `streamlit.testing.v1.AppTest`
    # (Playwright alone never reaches this code path without real Snowflake
    # credentials to get past the login gate) -- see Confluence SN space, SNOW-7.
    chat_page = st.Page(chat.render_page, title="Chat", icon=":material/chat:", url_path="chat", default=True)
    dashboards_page = st.Page(
        dashboards.render_page, title="Dashboards", icon=":material/bar_chart:", url_path="dashboards"
    )
    pg = st.navigation([chat_page, dashboards_page])
    pg.run()


def main() -> None:
    """Entry point: login gate first, then page navigation once authenticated."""
    _init_session_state()
    if _is_logged_in():
        _render_app()
    else:
        _render_login_form()


if __name__ == "__main__":
    main()
