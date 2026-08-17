"""Tests for pages_.fulfillment -- the Fulfillment Performance page's pure formatting helpers.

No Streamlit, no Snowflake, no network calls -- same split as
`test_dashboards_page.py`: `render_page`/`_ensure_filtered_data_loaded` are
Streamlit/Snowflake wiring and are not covered here.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pages_.fulfillment import (
    build_seller_ranking_table,
    format_count,
    format_days,
    format_delta_days,
    format_delta_pp,
    format_rate,
    style_seller_ranking_table,
)

# ── format_rate ──────────────────────────────────────────────────────────────


def test_format_rate_normal() -> None:
    assert format_rate(0.873) == "87.3%"


def test_format_rate_none_returns_dashes() -> None:
    assert format_rate(None) == "--"


def test_format_rate_nan_returns_dashes() -> None:
    assert format_rate(float("nan")) == "--"


# ── format_days ──────────────────────────────────────────────────────────────


def test_format_days_normal() -> None:
    assert format_days(11.234) == "11.2 days"


def test_format_days_none_returns_dashes() -> None:
    assert format_days(None) == "--"


# ── format_delta_pp ──────────────────────────────────────────────────────────


def test_format_delta_pp_positive() -> None:
    assert format_delta_pp(0.052) == "+5.2 pp"


def test_format_delta_pp_negative() -> None:
    assert format_delta_pp(-0.031) == "-3.1 pp"


def test_format_delta_pp_none_returns_none() -> None:
    assert format_delta_pp(None) is None


# ── format_delta_days ────────────────────────────────────────────────────────


def test_format_delta_days_positive() -> None:
    assert format_delta_days(1.5) == "+1.5 days"


def test_format_delta_days_negative() -> None:
    assert format_delta_days(-2.25) == "-2.2 days"


def test_format_delta_days_none_returns_none() -> None:
    assert format_delta_days(None) is None


# ── format_count ─────────────────────────────────────────────────────────────


def test_format_count_adds_thousands_separators() -> None:
    assert format_count(1234567) == "1,234,567"


def test_format_count_small_number_no_separator_needed() -> None:
    assert format_count(42) == "42"


def test_format_count_none_returns_dashes() -> None:
    assert format_count(None) == "--"


def test_format_count_nan_returns_dashes() -> None:
    assert format_count(float("nan")) == "--"


# ── build_seller_ranking_table ───────────────────────────────────────────────


def test_build_seller_ranking_table_renames_columns_in_order() -> None:
    ranking = pd.DataFrame(
        {
            "seller_id": ["seller_a"],
            "seller_state": ["SP"],
            "item_count": [10],
            "delivered_item_count": [9],
            "on_time_rate": [0.8],
            "avg_lead_time_days": [12.5],
        }
    )

    table = build_seller_ranking_table(ranking)

    assert list(table.columns) == ["Seller", "State", "Items", "Delivered", "On-Time Rate", "Avg Lead Time (days)"]
    assert table.loc[0, "Seller"] == "seller_a"
    assert table.loc[0, "On-Time Rate"] == pytest.approx(0.8)


def test_style_seller_ranking_table_formats_item_counts_with_thousands_separators() -> None:
    ranking = pd.DataFrame(
        {
            "seller_id": ["seller_a"],
            "seller_state": ["SP"],
            "item_count": [12345],
            "delivered_item_count": [12000],
            "on_time_rate": [0.8],
            "avg_lead_time_days": [12.5],
        }
    )

    table = build_seller_ranking_table(ranking)
    styled = style_seller_ranking_table(table)
    html = styled.to_html()

    assert "12,345" in html
    assert "12,000" in html
