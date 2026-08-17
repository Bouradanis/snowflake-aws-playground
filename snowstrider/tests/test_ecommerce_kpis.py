"""Tests for dashboards.ecommerce_kpis -- the e-commerce KPI dashboard backend.

No live Snowflake connection anywhere in this file: `get_virtual_today`,
`category_totals`, `weekly_trend`, and `category_kpi_report` are all
exercised against a `unittest.mock.MagicMock` standing in for a Snowpark
`Session` (matching the mocking style used for the Anthropic client in
`test_plot_chat.py`). `mat_window`/`ytd_window`/`_safe_pct_delta` are pure
functions and need no mocking at all.

Heaviest coverage is on the period-boundary math (`mat_window`/`ytd_window`)
and the delta math (`_safe_pct_delta`) -- these are the highest-bug-risk,
hardest-to-visually-verify code in this feature, so every expected date/
value below is written out explicitly rather than asserted for internal
consistency only.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboards.ecommerce_kpis import (
    _safe_pct_delta,
    category_kpi_report,
    category_totals,
    get_virtual_today,
    list_seller_states,
    mat_window,
    weekly_trend,
    ytd_window,
)

# ── mat_window / ytd_window ──────────────────────────────────────────────────
# Case A: an ordinary mid-year date, years_back = 0/1/2.
# Case B: a leap day (Feb 29 2024), to force the leap-year-safe relativedelta
#         path rather than a naive timedelta(days=365).
# Case C: Jan 1, the YTD boundary case where start == end.


def test_mat_window_years_back_0_ordinary_date() -> None:
    today = date(2026, 8, 14)
    assert mat_window(today, 0) == (date(2025, 8, 15), date(2026, 8, 14))


def test_mat_window_years_back_1_ordinary_date() -> None:
    today = date(2026, 8, 14)
    assert mat_window(today, 1) == (date(2024, 8, 15), date(2025, 8, 14))


def test_mat_window_years_back_2_ordinary_date() -> None:
    today = date(2026, 8, 14)
    assert mat_window(today, 2) == (date(2023, 8, 15), date(2024, 8, 14))


def test_mat_window_years_back_1_equals_mat_window_of_shifted_today() -> None:
    # Spec: mat_window(today, 1) == mat_window(today - 1 year, 0)
    today = date(2026, 8, 14)
    shifted_today = date(2025, 8, 14)
    assert mat_window(today, 1) == mat_window(shifted_today, 0)


def test_mat_window_leap_day_years_back_0() -> None:
    today = date(2024, 2, 29)
    # end - 1 year via relativedelta clamps Feb 29 -> Feb 28 2023, then +1 day.
    assert mat_window(today, 0) == (date(2023, 3, 1), date(2024, 2, 29))


def test_mat_window_leap_day_years_back_1() -> None:
    today = date(2024, 2, 29)
    assert mat_window(today, 1) == (date(2022, 3, 1), date(2023, 2, 28))


def test_ytd_window_years_back_0_ordinary_date() -> None:
    today = date(2026, 8, 14)
    assert ytd_window(today, 0) == (date(2026, 1, 1), date(2026, 8, 14))


def test_ytd_window_years_back_1_ordinary_date() -> None:
    today = date(2026, 8, 14)
    assert ytd_window(today, 1) == (date(2025, 1, 1), date(2025, 8, 14))


def test_ytd_window_years_back_2_ordinary_date() -> None:
    today = date(2026, 8, 14)
    assert ytd_window(today, 2) == (date(2024, 1, 1), date(2024, 8, 14))


def test_ytd_window_leap_day_years_back_0() -> None:
    today = date(2024, 2, 29)
    assert ytd_window(today, 0) == (date(2024, 1, 1), date(2024, 2, 29))


def test_ytd_window_leap_day_years_back_1() -> None:
    today = date(2024, 2, 29)
    # end clamps to Feb 28 2023 (2023 is not a leap year).
    assert ytd_window(today, 1) == (date(2023, 1, 1), date(2023, 2, 28))


def test_ytd_window_jan_1_start_equals_end() -> None:
    today = date(2023, 1, 1)
    assert ytd_window(today, 0) == (date(2023, 1, 1), date(2023, 1, 1))


def test_mat_window_jan_1() -> None:
    today = date(2023, 1, 1)
    assert mat_window(today, 0) == (date(2022, 1, 2), date(2023, 1, 1))


@pytest.mark.parametrize("window_fn", [mat_window, ytd_window])
def test_negative_years_back_raises(window_fn) -> None:
    with pytest.raises(ValueError):
        window_fn(date(2026, 1, 1), -1)


# ── _safe_pct_delta ──────────────────────────────────────────────────────────


def test_safe_pct_delta_normal_increase() -> None:
    assert _safe_pct_delta(120.0, 100.0) == pytest.approx(20.0)


def test_safe_pct_delta_normal_decrease() -> None:
    assert _safe_pct_delta(80.0, 100.0) == pytest.approx(-20.0)


def test_safe_pct_delta_year_ago_zero_returns_none() -> None:
    assert _safe_pct_delta(50.0, 0.0) is None


def test_safe_pct_delta_year_ago_nan_returns_none() -> None:
    assert _safe_pct_delta(50.0, float("nan")) is None


def test_safe_pct_delta_current_nan_returns_none() -> None:
    assert _safe_pct_delta(float("nan"), 50.0) is None


def test_safe_pct_delta_both_zero_returns_none() -> None:
    assert _safe_pct_delta(0.0, 0.0) is None


# ── get_virtual_today ─────────────────────────────────────────────────────────


def test_get_virtual_today_returns_max_plus_one_day() -> None:
    session = MagicMock()
    session.sql.return_value.collect.return_value = [(datetime(2018, 10, 17, 15, 30, 0),)]

    result = get_virtual_today(session)

    assert result == date(2018, 10, 18)


def test_get_virtual_today_raises_on_null_max() -> None:
    session = MagicMock()
    session.sql.return_value.collect.return_value = [(None,)]

    with pytest.raises(RuntimeError):
        get_virtual_today(session)


def test_get_virtual_today_raises_on_empty_result() -> None:
    session = MagicMock()
    session.sql.return_value.collect.return_value = []

    with pytest.raises(RuntimeError):
        get_virtual_today(session)


# ── category_totals ──────────────────────────────────────────────────────────


def _fake_pandas_result(columns_upper: dict) -> MagicMock:
    """Build a mock chained `session.sql(...).to_pandas()` return value."""
    query_result = MagicMock()
    query_result.to_pandas.return_value = pd.DataFrame(columns_upper)
    return query_result


def test_category_totals_builds_expected_sql_and_binds_params_positionally() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {
            "CATEGORY": ["toys"],
            "UNIT_SALES": [5],
            "VOLUME_SALES_KG": [1.2],
            "DOLLAR_SALES": [99.9],
        }
    )

    start_date, end_date = date(2025, 1, 1), date(2025, 2, 1)
    result = category_totals(session, start_date, end_date)

    session.sql.assert_called_once()
    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]

    assert "OLIST.RAW.ORDER_ITEMS" in sql_text
    assert "OLIST.RAW.ORDERS" in sql_text
    assert "OLIST.RAW.PRODUCTS" in sql_text
    assert "OLIST.RAW.PRODUCT_CATEGORY_NAME_TRANSLATION" in sql_text
    assert "GROUP BY pt.product_category_name_english" in sql_text
    assert sql_text.count("?") == 2  # qmark bind placeholders, not %(name)s
    assert call_kwargs["params"] == [start_date, end_date]

    # Result columns are lowercased regardless of Snowflake's uppercase alias casing.
    assert list(result.columns) == ["category", "unit_sales", "volume_sales_kg", "dollar_sales"]


def test_category_totals_rejects_inverted_window() -> None:
    session = MagicMock()
    with pytest.raises(ValueError):
        category_totals(session, date(2025, 2, 1), date(2025, 1, 1))


def test_category_totals_allows_zero_width_window() -> None:
    # start_date == end_date is legitimate (e.g. ytd_window(today, 0) when
    # today is Jan 1) and should just query/return an empty result, not raise.
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {"CATEGORY": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []}
    )
    result = category_totals(session, date(2026, 1, 1), date(2026, 1, 1))
    assert result.empty


# ── Seller Location filter (category_totals / weekly_trend) ─────────────────


def test_category_totals_with_seller_states_adds_in_clause_and_binds_params() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {"CATEGORY": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []}
    )

    start_date, end_date = date(2025, 1, 1), date(2025, 2, 1)
    category_totals(session, start_date, end_date, seller_states=["SP", "RJ"])

    session.sql.assert_called_once()
    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]

    assert "OLIST.RAW.SELLERS" in sql_text
    assert "s.seller_state IN (?, ?)" in sql_text
    assert sql_text.count("?") == 4  # 2 date bounds + 2 seller_state values
    assert call_kwargs["params"] == [start_date, end_date, "SP", "RJ"]


def test_category_totals_empty_seller_states_returns_empty_without_querying() -> None:
    session = MagicMock()
    result = category_totals(session, date(2025, 1, 1), date(2025, 2, 1), seller_states=[])

    session.sql.assert_not_called()
    assert result.empty
    assert list(result.columns) == ["category", "unit_sales", "volume_sales_kg", "dollar_sales"]


def test_category_totals_none_seller_states_matches_unfiltered_sql() -> None:
    # None is the default and must behave identically to omitting the arg --
    # no IN clause, no extra bind params.
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {"CATEGORY": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []}
    )
    category_totals(session, date(2025, 1, 1), date(2025, 2, 1), seller_states=None)

    call_args, call_kwargs = session.sql.call_args
    assert "seller_state IN" not in call_args[0]
    assert call_kwargs["params"] == [date(2025, 1, 1), date(2025, 2, 1)]


# ── order_status exclusion (canceled/unavailable never count as sales) ──────


def test_category_totals_excludes_canceled_and_unavailable_orders() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {"CATEGORY": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []}
    )
    category_totals(session, date(2025, 1, 1), date(2025, 2, 1))

    sql_text = session.sql.call_args[0][0]
    assert "o.order_status NOT IN ('canceled', 'unavailable')" in sql_text
    # Hardcoded status literals, not bind params -- date-window param count unchanged.
    assert session.sql.call_args[1]["params"] == [date(2025, 1, 1), date(2025, 2, 1)]


def test_weekly_trend_excludes_canceled_and_unavailable_orders() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {"ISO_WEEK": [], "ISO_YEAR": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []}
    )
    weekly_trend(session, virtual_today=date(2026, 8, 14))

    sql_text = session.sql.call_args[0][0]
    assert "o.order_status NOT IN ('canceled', 'unavailable')" in sql_text


# ── weekly_trend ──────────────────────────────────────────────────────────────


def test_weekly_trend_builds_expected_sql_and_uses_mat_window() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {
            "ISO_WEEK": [1],
            "ISO_YEAR": [2025],
            "UNIT_SALES": [10],
            "VOLUME_SALES_KG": [3.4],
            "DOLLAR_SALES": [200.0],
        }
    )

    virtual_today = date(2026, 8, 14)
    result = weekly_trend(session, virtual_today, years_back=1)

    session.sql.assert_called_once()
    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]

    assert "WEEKISO(o.order_approved_at)" in sql_text
    assert "YEAROFWEEKISO(o.order_approved_at)" in sql_text
    assert "GROUP BY iso_year, iso_week" in sql_text
    assert "ORDER BY iso_year, iso_week" in sql_text

    expected_start, expected_end = mat_window(virtual_today, 1)
    assert call_kwargs["params"] == [expected_start, expected_end]
    assert list(result.columns) == ["iso_week", "iso_year", "unit_sales", "volume_sales_kg", "dollar_sales"]


def test_weekly_trend_negative_years_back_raises() -> None:
    session = MagicMock()
    with pytest.raises(ValueError):
        weekly_trend(session, date(2026, 1, 1), years_back=-1)


def test_weekly_trend_with_seller_states_adds_in_clause_and_binds_params() -> None:
    session = MagicMock()
    session.sql.return_value = _fake_pandas_result(
        {"ISO_WEEK": [], "ISO_YEAR": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []}
    )

    virtual_today = date(2026, 8, 14)
    weekly_trend(session, virtual_today, years_back=0, seller_states=["SP"])

    call_args, call_kwargs = session.sql.call_args
    sql_text = call_args[0]
    expected_start, expected_end = mat_window(virtual_today, 0)

    assert "s.seller_state IN (?)" in sql_text
    assert call_kwargs["params"] == [expected_start, expected_end, "SP"]


def test_weekly_trend_empty_seller_states_returns_empty_without_querying() -> None:
    session = MagicMock()
    result = weekly_trend(session, date(2026, 1, 1), years_back=0, seller_states=[])

    session.sql.assert_not_called()
    assert result.empty
    assert list(result.columns) == ["iso_week", "iso_year", "unit_sales", "volume_sales_kg", "dollar_sales"]


# ── list_seller_states ───────────────────────────────────────────────────────


def test_list_seller_states_returns_values_in_query_order() -> None:
    session = MagicMock()
    session.sql.return_value.collect.return_value = [("AC",), ("RJ",), ("SP",)]

    result = list_seller_states(session)

    assert result == ["AC", "RJ", "SP"]
    call_args = session.sql.call_args[0]
    assert "DISTINCT seller_state" in call_args[0]
    assert "OLIST.RAW.SELLERS" in call_args[0]


def test_list_seller_states_empty_table_returns_empty_list() -> None:
    session = MagicMock()
    session.sql.return_value.collect.return_value = []

    assert list_seller_states(session) == []


# ── category_kpi_report ───────────────────────────────────────────────────────


def _sql_result(df: pd.DataFrame) -> MagicMock:
    result = MagicMock()
    result.to_pandas.return_value = df
    return result


def test_category_kpi_report_merges_four_windows_and_computes_deltas() -> None:
    session = MagicMock()

    # Call order inside category_kpi_report is: MAT current, MAT year-ago,
    # YTD current, YTD year-ago.
    mat_cur = pd.DataFrame(
        {
            "CATEGORY": ["toys", "electronics"],
            "UNIT_SALES": [100, 50],
            "VOLUME_SALES_KG": [200.0, 80.0],
            "DOLLAR_SALES": [1000.0, 500.0],
        }
    )
    # electronics has no MAT year-ago sales at all (category didn't exist yet).
    mat_ya = pd.DataFrame(
        {
            "CATEGORY": ["toys"],
            "UNIT_SALES": [80],
            "VOLUME_SALES_KG": [150.0],
            "DOLLAR_SALES": [800.0],
        }
    )
    # furniture is a category present only in YTD-current (brand new, no MAT
    # history and no YTD year-ago history either).
    ytd_cur = pd.DataFrame(
        {
            "CATEGORY": ["toys", "furniture"],
            "UNIT_SALES": [30, 10],
            "VOLUME_SALES_KG": [60.0, 20.0],
            "DOLLAR_SALES": [300.0, 100.0],
        }
    )
    ytd_ya = pd.DataFrame(
        {
            "CATEGORY": ["toys"],
            "UNIT_SALES": [40],
            "VOLUME_SALES_KG": [70.0],
            "DOLLAR_SALES": [400.0],
        }
    )

    session.sql.side_effect = [
        _sql_result(mat_cur),
        _sql_result(mat_ya),
        _sql_result(ytd_cur),
        _sql_result(ytd_ya),
    ]

    report = category_kpi_report(session, date(2026, 1, 1))

    assert session.sql.call_count == 4
    assert set(report["category"]) == {"toys", "electronics", "furniture"}

    by_category = report.set_index("category")

    # toys: present in all four windows -- ordinary delta math.
    assert by_category.loc["toys", "unit_sales_MAT"] == 100
    assert by_category.loc["toys", "unit_sales_MAT_ya"] == 80
    assert by_category.loc["toys", "unit_sales_MAT_delta_abs"] == 20
    assert by_category.loc["toys", "unit_sales_MAT_delta_pct"] == pytest.approx(25.0)
    assert by_category.loc["toys", "dollar_sales_YTD"] == 300.0
    assert by_category.loc["toys", "dollar_sales_YTD_ya"] == 400.0
    assert by_category.loc["toys", "dollar_sales_YTD_delta_pct"] == pytest.approx(-25.0)

    # electronics: present in MAT-current only -- MAT year-ago treated as 0,
    # so delta_pct must be undefined (NaN/None), never a ZeroDivisionError.
    assert by_category.loc["electronics", "unit_sales_MAT"] == 50
    assert by_category.loc["electronics", "unit_sales_MAT_ya"] == 0
    assert by_category.loc["electronics", "unit_sales_MAT_delta_abs"] == 50
    assert pd.isna(by_category.loc["electronics", "unit_sales_MAT_delta_pct"])
    # electronics never appears in either YTD window -- both sides 0, still no row drop.
    assert by_category.loc["electronics", "unit_sales_YTD"] == 0
    assert by_category.loc["electronics", "unit_sales_YTD_ya"] == 0
    assert pd.isna(by_category.loc["electronics", "unit_sales_YTD_delta_pct"])

    # furniture: present in YTD-current only -- MAT current/year-ago and YTD
    # year-ago are all missing -> treated as 0, row is still kept (not dropped).
    assert by_category.loc["furniture", "unit_sales_MAT"] == 0
    assert by_category.loc["furniture", "unit_sales_MAT_ya"] == 0
    assert pd.isna(by_category.loc["furniture", "unit_sales_MAT_delta_pct"])
    assert by_category.loc["furniture", "unit_sales_YTD"] == 10
    assert by_category.loc["furniture", "unit_sales_YTD_ya"] == 0
    assert by_category.loc["furniture", "unit_sales_YTD_delta_abs"] == 10
    assert pd.isna(by_category.loc["furniture", "unit_sales_YTD_delta_pct"])


def test_category_kpi_report_passes_seller_states_through_to_all_four_calls() -> None:
    session = MagicMock()
    empty = pd.DataFrame({"CATEGORY": [], "UNIT_SALES": [], "VOLUME_SALES_KG": [], "DOLLAR_SALES": []})
    session.sql.return_value = _sql_result(empty)

    category_kpi_report(session, date(2026, 1, 1), seller_states=["SP", "RJ"])

    assert session.sql.call_count == 4
    for call in session.sql.call_args_list:
        sql_text = call.args[0]
        params = call.kwargs["params"]
        assert "s.seller_state IN (?, ?)" in sql_text
        assert params[-2:] == ["SP", "RJ"]
