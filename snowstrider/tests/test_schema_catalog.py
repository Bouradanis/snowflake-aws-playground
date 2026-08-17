"""Tests for graph.schema_catalog -- table/column allowlist + business-term glossary rendering.

No Streamlit, no Snowflake, no network calls: both `format_schema_context`
and `format_business_glossary` are pure string builders.
"""

from __future__ import annotations

from graph.schema_catalog import format_business_glossary, format_schema_context


def test_format_schema_context_lists_all_nine_tables() -> None:
    context = format_schema_context()
    for table in (
        "CUSTOMERS", "SELLERS", "PRODUCT_CATEGORY_NAME_TRANSLATION", "PRODUCTS",
        "GEOLOCATION", "ORDERS", "ORDER_ITEMS", "ORDER_PAYMENTS", "ORDER_REVIEWS",
    ):
        assert f"OLIST.RAW.{table}" in context


# ── format_business_glossary ─────────────────────────────────────────────────


def test_business_glossary_defines_virtual_today_not_current_date() -> None:
    glossary = format_business_glossary()
    # The dataset is historical -- CURRENT_DATE()/CURRENT_TIMESTAMP() would be
    # years past the last real order, so the glossary must explicitly steer
    # the model away from them and toward MAX(order_approved_at).
    assert "CURRENT_DATE" in glossary
    assert "MAX(order_approved_at)" in glossary
    assert "OLIST.RAW.ORDERS" in glossary


def test_business_glossary_defines_mat() -> None:
    glossary = format_business_glossary()
    assert "MAT" in glossary
    assert "Moving Annual Total" in glossary


def test_business_glossary_defines_ytd() -> None:
    glossary = format_business_glossary()
    assert "YTD" in glossary
    assert "year to date" in glossary.lower()


def test_business_glossary_defines_year_ago_shift() -> None:
    glossary = format_business_glossary()
    assert "YA" in glossary
    assert "DATEADD" in glossary


def test_business_glossary_defines_revenue_as_price_not_freight() -> None:
    glossary = format_business_glossary()
    assert "SUM(oi.price)" in glossary
    assert "freight_value" in glossary  # mentioned as excluded from revenue


def test_business_glossary_defines_on_time_delivery_rate() -> None:
    glossary = format_business_glossary()
    assert "On-Time" in glossary or "on-time" in glossary.lower()
    assert "order_estimated_delivery_date" in glossary


def test_business_glossary_excludes_canceled_and_unavailable_orders() -> None:
    glossary = format_business_glossary()
    assert "'canceled'" in glossary
    assert "'unavailable'" in glossary
    assert "order_status" in glossary


def test_business_glossary_includes_top_n_with_ya_comparison_pattern() -> None:
    # The concrete gap this glossary is meant to close: "top N X for the
    # current period, with their YA figures" needs the CURRENT period's
    # top-N key set carried into the year-ago lookup via a join, not two
    # independent top-N queries (which could rank different products).
    glossary = format_business_glossary()
    assert "LEFT JOIN" in glossary
    assert "current_period" in glossary or "CURRENT_PERIOD" in glossary.upper()