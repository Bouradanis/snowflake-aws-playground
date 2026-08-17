"""Tests for dashboards.fulfillment -- the Fulfillment Performance dashboard backend.

Same mocking style as `test_ecommerce_kpis.py`: no live Snowflake connection
anywhere here, `session` is a `unittest.mock.MagicMock`. `_safe_ratio` and
`_safe_abs_delta` are pure functions and need no mocking.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboards.fulfillment import (
    _safe_abs_delta,
    _safe_ratio,
    fulfillment_kpi_report,
    fulfillment_totals,
    seller_fulfillment_ranking,
    weekly_on_time_trend,
)

# ── _safe_ratio ──────────────────────────────────────────────────────────────


def test_safe_ratio_normal() -> None:
    assert _safe_ratio(3, 4) == pytest.approx(0.75)


def test_safe_ratio_zero_denominator_returns_none() -> None:
    assert _safe_ratio(3, 0) is None


def test_safe_ratio_none_numerator_returns_none() -> None:
    assert _safe_ratio(None, 4) is None


def test_safe_ratio_none_denominator_returns_none() -> None:
    assert _safe_ratio(3, None) is None


# ── _safe_abs_delta ──────────────────────────────────────────────────────────


def test_safe_abs_delta_normal() -> None:
    assert _safe_abs_delta(0.9, 0.8) == pytest.approx(0.1)


def test_safe_abs_delta_current_none_returns_none() -> None:
    assert _safe_abs_delta(None, 0.8) is None


def test_safe_abs_delta_year_ago_none_returns_none() -> None:
    assert _safe_abs_delta(0.9, None) is None


# ── fulfillment_totals ───────────────────────────────────────────────────────


def _fake_collect_result(row: tuple) -> MagicMock:
    """Build a mock chained `session.sql(...).collect()` return value (one row)."""
    query_result = MagicMock()
    query_result.collect.return_value = [row]
    return query_result


def test_fulfillment_totals_builds_expected_sql_and_binds_params_positionally() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_collect_result((100, 90, 81, 900.0, 500.0, 5000.0))

    start_date, end_date = date(2025, 1, 1), date(2025, 2, 1)
    result = fulfillment_totals(session, start_date, end_date)

    session.sql.assert_called_once()
    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]

    assert "OLIST.RAW.ORDER_ITEMS" in sql_text
    assert "OLIST.RAW.ORDERS" in sql_text
    assert "OLIST.RAW.SELLERS" in sql_text
    assert "order_delivered_customer_date" in sql_text
    assert sql_text.count("?") == 2  # qmark bind placeholders, not %(name)s
    assert call_kwargs["params"] == [start_date, end_date]

    assert result["item_count"] == 100
    assert result["delivered_item_count"] == 90
    assert result["on_time_item_count"] == 81
    assert result["total_lead_time_days"] == pytest.approx(900.0)
    assert result["total_freight"] == pytest.approx(500.0)
    assert result["total_price"] == pytest.approx(5000.0)
    assert result["on_time_rate"] == pytest.approx(0.9)
    assert result["avg_lead_time_days"] == pytest.approx(10.0)
    assert result["freight_ratio"] == pytest.approx(0.1)


def test_fulfillment_totals_handles_decimal_row_values_from_collect() -> None:
    # Real Snowflake NUMBER columns come back from `Session.sql(...).collect()`
    # as `decimal.Decimal`, not `float` (`.to_pandas()` is what normalizes to
    # float64 -- `fulfillment_totals` uses `.collect()`, so it gets Decimals).
    session = MagicMock()
    session.sql.return_value = _fake_collect_result(
        (100, Decimal("90"), Decimal("81"), Decimal("900.0"), Decimal("500.00"), Decimal("5000.00"))
    )

    result = fulfillment_totals(session, date(2025, 1, 1), date(2025, 2, 1))

    assert result["on_time_rate"] == pytest.approx(0.9)
    assert result["avg_lead_time_days"] == pytest.approx(10.0)
    assert result["freight_ratio"] == pytest.approx(0.1)
    assert isinstance(result["freight_ratio"], float)


def test_fulfillment_kpi_report_handles_decimal_row_values_without_raising() -> None:
    # Regression: `ecommerce_kpis._safe_pct_delta` does `... * 100.0` (a float
    # literal) -- `Decimal * float` raises TypeError, so `fulfillment_totals`
    # must convert every Decimal to float before deltas are ever computed.
    session = MagicMock()
    session.sql.side_effect = [
        _fake_collect_result((100, Decimal("100"), Decimal("90"), Decimal("1000.0"), Decimal("100.00"), Decimal("1000.00"))),
        _fake_collect_result((100, Decimal("100"), Decimal("80"), Decimal("1000.0"), Decimal("200.00"), Decimal("1000.00"))),
        _fake_collect_result((50, Decimal("50"), Decimal("45"), Decimal("500.0"), Decimal("50.00"), Decimal("500.00"))),
        _fake_collect_result((50, Decimal("50"), Decimal("40"), Decimal("500.0"), Decimal("100.00"), Decimal("500.00"))),
    ]

    report = fulfillment_kpi_report(session, virtual_today=date(2026, 8, 14))

    assert report["on_time_rate_MAT_delta_pct"] == pytest.approx(12.5)


def test_fulfillment_totals_no_delivered_orders_ratios_are_none() -> None:
    session = MagicMock()
    # item_count=5, but nothing delivered yet -> delivered/on_time/lead_time all 0,
    # and SUM(freight)/SUM(price) come back NULL from Snowflake (no matching rows
    # for those aggregates isn't the case here since items exist, but exercise the
    # NULL-from-SQL path explicitly since Snowflake SUM() of an all-NULL set is NULL).
    session.sql.return_value = _fake_collect_result((5, 0, 0, 0, None, None))

    result = fulfillment_totals(session, date(2025, 1, 1), date(2025, 2, 1))

    assert result["item_count"] == 5
    assert result["delivered_item_count"] == 0
    assert result["on_time_rate"] is None
    assert result["avg_lead_time_days"] is None
    assert result["freight_ratio"] is None


def test_fulfillment_totals_rejects_inverted_window() -> None:
    session = MagicMock()
    with pytest.raises(ValueError):
        fulfillment_totals(session, date(2025, 2, 1), date(2025, 1, 1))


def test_fulfillment_totals_with_seller_states_adds_in_clause_and_binds_params() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_collect_result((0, 0, 0, 0, 0, 0))

    start_date, end_date = date(2025, 1, 1), date(2025, 2, 1)
    fulfillment_totals(session, start_date, end_date, seller_states=["SP", "RJ"])

    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]
    assert "s.seller_state IN (?, ?)" in sql_text
    assert sql_text.count("?") == 4
    assert call_kwargs["params"] == [start_date, end_date, "SP", "RJ"]


def test_fulfillment_totals_empty_seller_states_returns_zeroed_without_querying() -> None:
    session = MagicMock()
    result = fulfillment_totals(session, date(2025, 1, 1), date(2025, 2, 1), seller_states=[])

    session.sql.assert_not_called()
    assert result["item_count"] == 0
    assert result["on_time_rate"] is None
    assert result["avg_lead_time_days"] is None
    assert result["freight_ratio"] is None


# ── order_status exclusion (canceled/unavailable never count as fulfillment) ─


def test_fulfillment_totals_excludes_canceled_and_unavailable_orders() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_collect_result((0, 0, 0, 0, 0, 0))
    fulfillment_totals(session, date(2025, 1, 1), date(2025, 2, 1))

    sql_text = session.sql.call_args[0][0]
    assert "o.order_status NOT IN ('canceled', 'unavailable')" in sql_text


# ── fulfillment_kpi_report ───────────────────────────────────────────────────


def test_fulfillment_kpi_report_computes_deltas_across_four_windows() -> None:
    session = MagicMock()
    # 4 calls in order: MAT current, MAT year-ago, YTD current, YTD year-ago.
    session.sql.side_effect = [
        _fake_collect_result((100, 100, 90, 1000.0, 100.0, 1000.0)),  # MAT cur: on_time=.9 lead=10 freight=.1
        _fake_collect_result((100, 100, 80, 1000.0, 200.0, 1000.0)),  # MAT ya: on_time=.8 lead=10 freight=.2
        _fake_collect_result((50, 50, 45, 500.0, 50.0, 500.0)),  # YTD cur: on_time=.9 lead=10 freight=.1
        _fake_collect_result((50, 50, 40, 500.0, 100.0, 500.0)),  # YTD ya: on_time=.8 lead=10 freight=.2
    ]

    report = fulfillment_kpi_report(session, virtual_today=date(2026, 8, 14))

    assert session.sql.call_count == 4
    assert report["on_time_rate_MAT"] == pytest.approx(0.9)
    assert report["on_time_rate_MAT_ya"] == pytest.approx(0.8)
    assert report["on_time_rate_MAT_delta_abs"] == pytest.approx(0.1)
    assert report["on_time_rate_MAT_delta_pct"] == pytest.approx(12.5)
    assert report["freight_ratio_YTD"] == pytest.approx(0.1)
    assert report["freight_ratio_YTD_ya"] == pytest.approx(0.2)
    assert report["freight_ratio_YTD_delta_abs"] == pytest.approx(-0.1)


def test_fulfillment_kpi_report_none_year_ago_yields_none_deltas() -> None:
    session = MagicMock()
    session.sql.side_effect = [
        _fake_collect_result((10, 10, 9, 100.0, 10.0, 100.0)),
        _fake_collect_result((0, 0, 0, 0, None, None)),  # no year-ago data at all
        _fake_collect_result((10, 10, 9, 100.0, 10.0, 100.0)),
        _fake_collect_result((0, 0, 0, 0, None, None)),
    ]

    report = fulfillment_kpi_report(session, virtual_today=date(2026, 8, 14))

    assert report["on_time_rate_MAT"] == pytest.approx(0.9)
    assert report["on_time_rate_MAT_ya"] is None
    assert report["on_time_rate_MAT_delta_abs"] is None
    assert report["on_time_rate_MAT_delta_pct"] is None


# ── seller_fulfillment_ranking ───────────────────────────────────────────────


def _fake_pandas_result(columns_upper: dict) -> MagicMock:
    query_result = MagicMock()
    query_result.to_pandas.return_value = pd.DataFrame(columns_upper)
    return query_result


def test_seller_fulfillment_ranking_builds_expected_sql_and_computes_rates() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {
            "SELLER_ID": ["seller_a", "seller_b"],
            "SELLER_STATE": ["SP", "RJ"],
            "ITEM_COUNT": [10, 5],
            "DELIVERED_ITEM_COUNT": [10, 0],
            "ON_TIME_ITEM_COUNT": [8, 0],
            "TOTAL_LEAD_TIME_DAYS": [100.0, 0.0],
        }
    )

    start_date, end_date = date(2025, 1, 1), date(2025, 2, 1)
    result = seller_fulfillment_ranking(session, start_date, end_date)

    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]
    assert "GROUP BY s.seller_id, s.seller_state" in sql_text
    assert call_kwargs["params"] == [start_date, end_date]

    assert list(result["seller_id"]) == ["seller_a", "seller_b"]
    assert result.loc[0, "on_time_rate"] == pytest.approx(0.8)
    assert result.loc[0, "avg_lead_time_days"] == pytest.approx(10.0)
    # seller_b has zero delivered items -> ratios are NaN/None, not a ZeroDivisionError.
    assert pd.isna(result.loc[1, "on_time_rate"])


def test_seller_fulfillment_ranking_empty_seller_states_returns_empty_without_querying() -> None:
    session = MagicMock()
    result = seller_fulfillment_ranking(session, date(2025, 1, 1), date(2025, 2, 1), seller_states=[])

    session.sql.assert_not_called()
    assert result.empty
    assert list(result.columns) == [
        "seller_id",
        "seller_state",
        "item_count",
        "delivered_item_count",
        "on_time_rate",
        "avg_lead_time_days",
    ]


# ── weekly_on_time_trend ─────────────────────────────────────────────────────


def test_weekly_on_time_trend_builds_expected_sql_and_computes_rates() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {
            "ISO_WEEK": [33],
            "ISO_YEAR": [2026],
            "ITEM_COUNT": [20],
            "DELIVERED_ITEM_COUNT": [20],
            "ON_TIME_ITEM_COUNT": [18],
            "TOTAL_LEAD_TIME_DAYS": [200.0],
        }
    )

    result = weekly_on_time_trend(session, virtual_today=date(2026, 8, 14), years_back=0)

    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]
    assert "GROUP BY iso_year, iso_week" in sql_text
    assert "ORDER BY iso_year, iso_week" in sql_text

    assert result.loc[0, "on_time_rate"] == pytest.approx(0.9)
    assert result.loc[0, "avg_lead_time_days"] == pytest.approx(10.0)


def test_weekly_on_time_trend_empty_seller_states_returns_empty_without_querying() -> None:
    session = MagicMock()
    result = weekly_on_time_trend(session, virtual_today=date(2026, 8, 14), seller_states=[])

    session.sql.assert_not_called()
    assert result.empty
    assert list(result.columns) == ["iso_week", "iso_year", "on_time_rate", "avg_lead_time_days"]


def test_weekly_on_time_trend_excludes_canceled_and_unavailable_orders() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {
            "ISO_WEEK": [], "ISO_YEAR": [], "ITEM_COUNT": [], "DELIVERED_ITEM_COUNT": [],
            "ON_TIME_ITEM_COUNT": [], "TOTAL_LEAD_TIME_DAYS": [],
        }
    )
    weekly_on_time_trend(session, virtual_today=date(2026, 8, 14))

    sql_text = session.sql.call_args[0][0]
    assert "o.order_status NOT IN ('canceled', 'unavailable')" in sql_text


def test_seller_fulfillment_ranking_excludes_canceled_and_unavailable_orders() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {
            "SELLER_ID": [], "SELLER_STATE": [], "ITEM_COUNT": [], "DELIVERED_ITEM_COUNT": [],
            "ON_TIME_ITEM_COUNT": [], "TOTAL_LEAD_TIME_DAYS": [],
        }
    )
    seller_fulfillment_ranking(session, date(2025, 1, 1), date(2025, 2, 1))

    sql_text = session.sql.call_args[0][0]
    assert "o.order_status NOT IN ('canceled', 'unavailable')" in sql_text
