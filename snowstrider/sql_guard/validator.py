"""SELECT-only, allowlist-enforced SQL validator for LLM-generated SQL.

This is the last line of defense between an Anthropic-generated query string
and a live Snowflake warehouse. It is deliberately an ALLOWLIST (only
SELECT/WITH statements, only OLIST.RAW tables) rather than a blocklist of
"dangerous" keywords -- allowlists degrade safely (an unrecognized construct
is rejected), blocklists degrade unsafely (an unrecognized construct is
silently permitted).

Standalone and dependency-light on purpose: importable and testable without a
Snowflake session, an Anthropic client, or any part of the langgraph wiring.
"""

from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp

from graph.schema_catalog import TABLE_NAMES

logger = logging.getLogger(__name__)

DEFAULT_DATABASE = "OLIST"
DEFAULT_SCHEMA = "RAW"
MAX_LIMIT = 500

# Defense-in-depth: cheap case-insensitive substring scan of the raw SQL text,
# in case sqlglot's Snowflake dialect has a coverage gap and lets one of these
# through as some other expression type (e.g. a bare Command it doesn't
# otherwise recognize, or a future dialect change). Checked *in addition to*
# the AST-based checks below, never instead of them.
_FORBIDDEN_SUBSTRINGS = (
    "EXECUTE IMMEDIATE",
    "COPY INTO",
    " PUT ",
    " GET ",
    "SYSTEM$",
)


def _contains_forbidden_substring(sql: str) -> str | None:
    """Return the matched forbidden substring if found (case-insensitive), else None."""
    upper_sql = f" {sql.upper()} "  # pad so leading/trailing ' PUT '/' GET ' still match
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        if forbidden in upper_sql:
            return forbidden.strip()
    return None


def _cte_names(statement: exp.Expression) -> set[str]:
    """Collect uppercased CTE alias names defined anywhere in the statement.

    CTE aliases show up as ordinary `exp.Table` references at their use site
    (e.g. `FROM cte`), so they must be excluded from the allowlist check --
    they are not real OLIST.RAW tables, they're local names for a subquery.
    """
    return {cte.alias.upper() for cte in statement.find_all(exp.CTE) if cte.alias}


def _validate_table_references(statement: exp.Expression) -> str | None:
    """Return an error message if any table reference is outside the allowlist, else None."""
    cte_names = _cte_names(statement)
    for table in statement.find_all(exp.Table):
        name = (table.name or "").upper()
        if not name or name in cte_names:
            continue

        db = (table.db or "").upper()
        catalog = (table.catalog or "").upper()

        if catalog and catalog != DEFAULT_DATABASE:
            return f"table reference '{table.sql()}' is outside the OLIST database"
        if db and db != DEFAULT_SCHEMA:
            return f"table reference '{table.sql()}' is outside the OLIST.RAW schema"
        if name not in TABLE_NAMES:
            return f"table '{name}' is not in the OLIST.RAW allowlist"

    return None


def _is_select_or_cte_select(statement: exp.Expression) -> bool:
    """True if `statement` is a bare SELECT, or a WITH whose wrapped query is a SELECT."""
    if isinstance(statement, exp.Select):
        return True
    if isinstance(statement, exp.With):
        return isinstance(statement.this, exp.Select)
    return False


def validate(sql: str) -> tuple[bool, str | None, str | None]:
    """Validate an LLM-generated SQL string against the OLIST.RAW allowlist.

    Returns ``(is_valid, cleaned_sql, error_message)``:

    - On success: ``(True, cleaned_sql, None)`` where ``cleaned_sql`` is the
      AST round-tripped, LIMIT-capped, re-serialized statement. This is the
      *only* string that should ever be executed against Snowflake -- never
      the raw input.
    - On failure: ``(False, None, error_message)``.

    Validation order:
    1. Parse must yield exactly one statement (blocks `;`-delimited
       multi-statement injection, even if every statement is individually a
       benign SELECT).
    2. The statement must be a SELECT (bare or WITH-wrapped) -- allowlist,
       not a blocklist.
    3. Every referenced table must resolve to one of the OLIST.RAW tables in
       `graph.schema_catalog.OLIST_RAW_TABLES` (bare or fully-qualified).
    4. Defense-in-depth substring scan for constructs sqlglot's Snowflake
       dialect might mis-parse (EXECUTE IMMEDIATE, COPY INTO, PUT, GET,
       SYSTEM$).
    5. Add a `LIMIT 500` if none is present; preserve an existing LIMIT as-is.
    """
    if not sql or not sql.strip():
        return False, None, "empty SQL"

    forbidden = _contains_forbidden_substring(sql)
    if forbidden:
        logger.warning("sql_guard rejected query containing forbidden construct: %s", forbidden)
        return False, None, f"forbidden construct detected: {forbidden}"

    try:
        statements = [s for s in sqlglot.parse(sql, dialect="snowflake") if s is not None]
    except sqlglot.errors.ParseError as exc:
        logger.warning("sql_guard failed to parse SQL: %s", exc)
        return False, None, f"could not parse SQL: {exc}"

    if len(statements) != 1:
        logger.warning("sql_guard rejected multi-statement SQL (%d statements)", len(statements))
        return False, None, f"expected exactly one statement, found {len(statements)}"

    statement = statements[0]

    if not _is_select_or_cte_select(statement):
        logger.warning("sql_guard rejected non-SELECT statement of type %s", type(statement).__name__)
        return False, None, f"only SELECT statements are allowed, got {type(statement).__name__}"

    table_error = _validate_table_references(statement)
    if table_error:
        logger.warning("sql_guard rejected query: %s", table_error)
        return False, None, table_error

    # Re-serialize the *parsed* statement (never the raw input string) after
    # capping the LIMIT. `.limit()` only appends a LIMIT clause when the
    # query doesn't already have one -- an existing LIMIT is left untouched
    # even if it's higher than MAX_LIMIT is not enforced here (spec: preserve
    # an existing LIMIT as-is; MAX_LIMIT only applies when adding one).
    if statement.args.get("limit") is None:
        statement = statement.limit(MAX_LIMIT)

    cleaned_sql = statement.sql(dialect="snowflake")
    return True, cleaned_sql, None
