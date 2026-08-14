"""validate_sql node -- runs the sql_guard allowlist validator against sql_candidate."""

from __future__ import annotations

import logging

from graph.state import SnowstriderState
from sql_guard.validator import validate

logger = logging.getLogger(__name__)


def validate_sql(state: SnowstriderState) -> dict:
    """Validate `state["sql_candidate"]` via `sql_guard.validator.validate`.

    On success: `sql_candidate` becomes the cleaned (LIMIT-capped,
    re-serialized) SQL and `validation_error` is cleared.
    On failure: `validation_error` is set to the failure reason and
    `sql_candidate` is left as the invalid raw SQL -- needed for the retry
    feedback prompt in `generate_sql`, but never used for execution
    (`execute_sql` only ever runs cleaned SQL that passed this check).

    No external bindings needed (no Snowflake/Anthropic dependency), so this
    is a plain function usable directly as a graph node -- no factory wrapper.
    """
    sql_candidate = state.get("sql_candidate")
    if not sql_candidate:
        logger.warning("validate_sql: no SQL candidate to validate")
        return {"validation_error": "no SQL was generated"}

    is_valid, cleaned_sql, error_message = validate(sql_candidate)

    if is_valid:
        logger.info("validate_sql: query passed validation")
        return {"sql_candidate": cleaned_sql, "validation_error": None}

    logger.warning("validate_sql: query rejected: %s", error_message)
    return {"validation_error": error_message}
