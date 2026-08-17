"""Connection helpers for Snowstrider: Snowpark `Session` and Anthropic client.

Unlike the rest of this repo's `.env`-based scripts (see
`coursera/Module_2/connect_to_db.py`), Snowstrider is a standalone Streamlit
app with a per-user login form -- so `get_session` takes credentials as
explicit function arguments rather than reading `SNOWFLAKE_*` out of the
environment. `get_anthropic_client` still falls back to `.env` for local/test
runs where there's no Streamlit secrets store.
"""

from __future__ import annotations

import logging
import os

import anthropic
from dotenv import load_dotenv
from snowflake.snowpark import Session

logger = logging.getLogger(__name__)

DEFAULT_WAREHOUSE = "COMPUTE_WH"
DEFAULT_DATABASE = "OLIST"
DEFAULT_SCHEMA = "RAW"


def get_session(
    account: str,
    user: str,
    password: str,
    warehouse: str = DEFAULT_WAREHOUSE,
    database: str = DEFAULT_DATABASE,
    schema: str = DEFAULT_SCHEMA,
) -> Session:
    """Build a Snowpark `Session` from explicit, caller-supplied credentials.

    Credentials come from function arguments (e.g. a Streamlit login form),
    NOT from `.env` -- this app is meant to run with a per-user login, unlike
    the rest of this repo's scripts. Reuses the same connection-parameter key
    names as `coursera/Module_2/connect_to_db.py` for consistency.

    Raises:
        ValueError: if `account`, `user`, or `password` is empty.
        snowflake.snowpark.exceptions.SnowparkSQLException: if Snowflake
            rejects the connection (bad credentials, unreachable account, etc).
    """
    if not account or not user or not password:
        raise ValueError("account, user, and password are all required to open a Snowflake session")

    connection_parameters = {
        "account": account,
        "user": user,
        "password": password,
        "warehouse": warehouse,
        "database": database,
        "schema": schema,
    }

    logger.info("Opening Snowpark session: account=%s user=%s warehouse=%s database=%s schema=%s",
                account, user, warehouse, database, schema)
    return Session.builder.configs(connection_parameters).create()


def get_anthropic_client() -> anthropic.Anthropic:
    """Build an Anthropic client, resolving the API key with this priority:

    1. `st.secrets["ANTHROPIC_API_KEY"]`, if Streamlit secrets are configured
       (accessing `st.secrets` raises when no `secrets.toml` exists -- e.g.
       during local non-Streamlit test runs -- so that's caught and treated
       as "not available", not a fatal error).
    2. `os.environ["ANTHROPIC_API_KEY"]`, loaded via `python-dotenv`'s
       `load_dotenv()` against the repo-root `.env`, matching this repo's
       established pattern.

    Raises:
        RuntimeError: if neither source has the key set -- never silently
            builds a client with `api_key=None`.
    """
    api_key = _api_key_from_streamlit_secrets()
    if not api_key:
        api_key = _api_key_from_dotenv()

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not found in Streamlit secrets or the environment/.env. "
            "Set it in .streamlit/secrets.toml (deployed) or the repo-root .env (local)."
        )

    return anthropic.Anthropic(api_key=api_key)


def _api_key_from_streamlit_secrets() -> str | None:
    """Return ANTHROPIC_API_KEY from `st.secrets`, or None if unavailable."""
    try:
        import streamlit as st

        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        # Covers: streamlit not installed in this context, no secrets.toml
        # present (st.secrets raises), or the key simply isn't set there.
        return None


def _api_key_from_dotenv() -> str | None:
    """Return ANTHROPIC_API_KEY from the environment after loading repo-root .env."""
    load_dotenv()
    return os.environ.get("ANTHROPIC_API_KEY")
