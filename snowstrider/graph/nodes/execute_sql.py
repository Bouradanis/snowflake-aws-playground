"""execute_sql node -- runs the cleaned SQL against Snowflake via a bound Snowpark session.

DESIGN NOTE -- full-result handoff (spec offered two legitimate options, this
is the one picked, and why): `SnowstriderState` must stay small/serializable,
so this node does NOT put the full result DataFrame into state -- only
`result_columns` / `result_row_count` / a 10-row `result_preview`. The full
DataFrame is cached in a module-level in-memory registry
(`_RESULT_REGISTRY`), keyed by the *cleaned SQL text itself* (which already
lives in `state["sql_candidate"]` once validation succeeds -- no new state
key needed, so `graph/state.py` stays exactly as specified). `app.py` is
expected to call `get_result(state["sql_candidate"])` after `graph.invoke()`
returns to get the full DataFrame, rather than re-running the SQL a second
time against Snowflake -- re-executing would cost a second warehouse
round-trip, which this repo's CLAUDE.md explicitly flags as the binding cost
constraint on this project.

The registry is capped at `_REGISTRY_MAX_ENTRIES` (evicting oldest-first) so a
long-running Streamlit session doesn't grow this dict unbounded -- it's a
process-local cache, not a persisted store, and is not thread-safe (fine for
a single-user local Streamlit session; would need `st.session_state` or a
real cache for multi-user hosting).
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Callable, Optional

import pandas as pd
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException

from graph.state import SnowstriderState

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 10
_REGISTRY_MAX_ENTRIES = 50

_RESULT_REGISTRY: "OrderedDict[str, pd.DataFrame]" = OrderedDict()


def get_result(cleaned_sql: str) -> Optional[pd.DataFrame]:
    """Retrieve the full DataFrame for a previously executed cleaned SQL string, if still cached."""
    return _RESULT_REGISTRY.get(cleaned_sql)


def _cache_result(cleaned_sql: str, df: pd.DataFrame) -> None:
    _RESULT_REGISTRY[cleaned_sql] = df
    _RESULT_REGISTRY.move_to_end(cleaned_sql)
    while len(_RESULT_REGISTRY) > _REGISTRY_MAX_ENTRIES:
        _RESULT_REGISTRY.popitem(last=False)


def make_execute_sql_node(session: Session) -> Callable[[SnowstriderState], dict]:
    """Build the `execute_sql` node, closing over a Snowpark session bound at graph build time."""

    def execute_sql(state: SnowstriderState) -> dict:
        """Run `state["sql_candidate"]` (the cleaned SQL) and summarize the result into state."""
        cleaned_sql = state.get("sql_candidate")
        if not cleaned_sql:
            logger.error("execute_sql: no cleaned SQL available to execute")
            return {"execution_error": "no validated SQL available to execute"}

        try:
            df = session.sql(cleaned_sql).to_pandas()
        except SnowparkSQLException as exc:
            logger.error("execute_sql: query failed: %s", exc)
            return {"execution_error": str(exc)}

        _cache_result(cleaned_sql, df)

        preview = df.head(PREVIEW_ROWS).to_dict("records")
        logger.info("execute_sql: query returned %d rows", len(df))

        return {
            "result_columns": list(df.columns),
            "result_row_count": len(df),
            "result_preview": preview,
            "execution_error": None,
        }

    return execute_sql
