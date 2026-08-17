"""Tests for sql_guard.validator -- the allowlist-based SQL validator.

No network calls, no Snowflake/Anthropic dependency -- pure AST checks via
sqlglot against the hardcoded OLIST.RAW allowlist.
"""

from __future__ import annotations

import pytest

from sql_guard.validator import validate

VALID_SIMPLE_SELECT = "SELECT customer_id, customer_state FROM OLIST.RAW.CUSTOMERS"

VALID_JOIN = """
SELECT o.order_id, c.customer_state
FROM OLIST.RAW.ORDERS o
JOIN OLIST.RAW.CUSTOMERS c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
"""

VALID_CTE = """
WITH order_totals AS (
    SELECT order_id, SUM(price) AS total_price
    FROM OLIST.RAW.ORDER_ITEMS
    GROUP BY order_id
)
SELECT * FROM order_totals WHERE total_price > 100
"""

MULTI_STATEMENT_INJECTION = "SELECT 1; DROP TABLE OLIST.RAW.ORDERS;"

CROSS_SCHEMA_REFERENCE = "SELECT * FROM OTHER_DB.OTHER_SCHEMA.SECRET"

DML_INSERT = "INSERT INTO OLIST.RAW.ORDERS (order_id) VALUES ('x')"
DML_DELETE = "DELETE FROM OLIST.RAW.ORDERS WHERE order_id = 'x'"
DDL_CREATE = "CREATE TABLE evil (id INT)"

EXECUTE_IMMEDIATE_IN_STRING_LITERAL = "SELECT 'EXECUTE IMMEDIATE nope' AS decoy FROM OLIST.RAW.ORDERS"

BENIGN_MULTI_STATEMENT = "SELECT 1; SELECT 2;"

NO_LIMIT_SELECT = "SELECT * FROM OLIST.RAW.ORDERS"
EXISTING_LIMIT_SELECT = "SELECT * FROM OLIST.RAW.ORDERS LIMIT 10"


@pytest.mark.parametrize(
    "sql,expected_valid",
    [
        (VALID_SIMPLE_SELECT, True),
        (VALID_JOIN, True),
        (VALID_CTE, True),
        (MULTI_STATEMENT_INJECTION, False),
        (CROSS_SCHEMA_REFERENCE, False),
        (DML_INSERT, False),
        (DML_DELETE, False),
        (DDL_CREATE, False),
        (EXECUTE_IMMEDIATE_IN_STRING_LITERAL, False),
        (BENIGN_MULTI_STATEMENT, False),
    ],
)
def test_validate_expected_outcome(sql: str, expected_valid: bool) -> None:
    is_valid, cleaned_sql, error_message = validate(sql)
    assert is_valid is expected_valid
    if expected_valid:
        assert cleaned_sql is not None
        assert error_message is None
    else:
        assert cleaned_sql is None
        assert error_message is not None


def test_no_limit_gets_one_added() -> None:
    is_valid, cleaned_sql, _ = validate(NO_LIMIT_SELECT)
    assert is_valid
    assert "LIMIT 500" in cleaned_sql.upper()


def test_existing_limit_is_preserved_not_overridden() -> None:
    is_valid, cleaned_sql, _ = validate(EXISTING_LIMIT_SELECT)
    assert is_valid
    assert "LIMIT 10" in cleaned_sql.upper()
    assert "LIMIT 500" not in cleaned_sql.upper()


def test_cross_schema_reference_error_mentions_the_reason() -> None:
    is_valid, cleaned_sql, error_message = validate(CROSS_SCHEMA_REFERENCE)
    assert not is_valid
    assert cleaned_sql is None
    assert "OTHER_DB" in error_message or "database" in error_message.lower() or "schema" in error_message.lower()


def test_multi_statement_injection_is_rejected_even_if_first_statement_is_benign() -> None:
    is_valid, cleaned_sql, error_message = validate(MULTI_STATEMENT_INJECTION)
    assert not is_valid
    assert cleaned_sql is None
    assert "statement" in error_message.lower()


def test_execute_immediate_wrapped_in_string_literal_is_still_rejected() -> None:
    # This one should trip the defense-in-depth substring scan even though
    # the AST sees a harmless string literal, not an EXECUTE IMMEDIATE command.
    is_valid, cleaned_sql, error_message = validate(EXECUTE_IMMEDIATE_IN_STRING_LITERAL)
    assert not is_valid
    assert cleaned_sql is None


def test_empty_sql_is_rejected() -> None:
    is_valid, cleaned_sql, error_message = validate("")
    assert not is_valid
    assert cleaned_sql is None
    assert error_message is not None


def test_bare_unqualified_table_name_is_allowed() -> None:
    # Bare table references assume OLIST.RAW context.
    is_valid, cleaned_sql, error_message = validate("SELECT * FROM ORDERS")
    assert is_valid, error_message
