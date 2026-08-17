"""Tests for pages_.dashboards -- the Dashboards page's pure formatting/wiring helpers.

No Streamlit, no Snowflake, no network calls: `format_compact`,
`format_measure_value`, `format_delta_abs`, `format_delta_pct`,
`style_delta_cell_value`, `build_kpi_table`, `style_kpi_table`, and
`align_weekly_trend` are all pure functions of DataFrames/values in. `render_page`
and `_ensure_data_loaded` (Streamlit/Snowflake wiring) are intentionally not
covered here -- verified live via Playwright instead (boot-level check only,
since there's no live Snowflake session in this test environment).

`build_kpi_table` deliberately stays numeric (not pre-formatted display
strings) -- see `style_kpi_table`'s docstring for why: `st.dataframe`'s
interactive column-sort operates on the DataFrame's real dtype, and an
earlier, string-based version of this table made "sort descending" a
lexicographic string sort instead of a numeric one. Display formatting and
delta-cell coloring live in `style_kpi_table`, which returns a
`pandas.io.formats.style.Styler` -- checked here via `.to_html()`, since a
Styler's formatted/colored output isn't otherwise directly inspectable.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from pages_.dashboards import (
    align_weekly_trend,
    build_kpi_table,
    build_trend_chart,
    format_compact,
    format_delta_abs,
    format_delta_pct,
    format_measure_value,
    resolve_seller_states_filter,
    seller_checkbox_key,
    style_delta_cell_value,
    style_kpi_table,
    summarize_seller_selection,
)

# ── format_compact ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),
        (284, "284"),
        (1_284, "1.3K"),
        (12_900, "12.9K"),
        (999_999, "1000.0K"),
        (1_200_000, "1.2M"),
        (3_400_000_000, "3.4B"),
        (-1_284, "-1.3K"),
        (-284, "-284"),
    ],
)
def test_format_compact_thresholds(value: float, expected: str) -> None:
    assert format_compact(value) == expected


def test_format_compact_none_is_dashes() -> None:
    assert format_compact(None) == "--"


def test_format_compact_nan_is_dashes() -> None:
    assert format_compact(float("nan")) == "--"


# ── format_measure_value ─────────────────────────────────────────────────────


def test_format_measure_value_dollar_measure_gets_prefix() -> None:
    assert format_measure_value(1_284, "dollar_sales") == "$1.3K"


def test_format_measure_value_non_dollar_measure_has_no_prefix() -> None:
    assert format_measure_value(1_284, "unit_sales") == "1.3K"
    assert format_measure_value(1_284, "volume_sales_kg") == "1.3K"


# ── format_delta_abs / format_delta_pct ──────────────────────────────────────


def test_format_delta_abs_positive_has_up_arrow_and_plus_sign() -> None:
    assert format_delta_abs(500, "unit_sales") == "▲ +500"


def test_format_delta_abs_negative_has_down_arrow_and_minus_sign() -> None:
    assert format_delta_abs(-500, "unit_sales") == "▼ -500"


def test_format_delta_abs_zero_is_flat_glyph_no_sign() -> None:
    assert format_delta_abs(0, "unit_sales") == "• 0"


def test_format_delta_abs_dollar_measure_prefixes_dollar_after_sign() -> None:
    assert format_delta_abs(1_500, "dollar_sales") == "▲ +$1.5K"
    assert format_delta_abs(-1_500, "dollar_sales") == "▼ -$1.5K"


def test_format_delta_abs_none_is_dashes() -> None:
    assert format_delta_abs(None, "unit_sales") == "--"


def test_format_delta_abs_nan_is_dashes() -> None:
    assert format_delta_abs(math.nan, "unit_sales") == "--"


def test_format_delta_pct_positive() -> None:
    assert format_delta_pct(12.34) == "▲ +12.3%"


def test_format_delta_pct_negative() -> None:
    assert format_delta_pct(-5.0) == "▼ -5.0%"


def test_format_delta_pct_zero_is_flat() -> None:
    assert format_delta_pct(0) == "• 0.0%"


def test_format_delta_pct_none_is_dashes() -> None:
    assert format_delta_pct(None) == "--"


def test_format_delta_pct_nan_is_dashes() -> None:
    assert format_delta_pct(float("nan")) == "--"


# ── style_delta_cell_value ────────────────────────────────────────────────────


def test_style_delta_cell_value_positive_is_positive_color() -> None:
    assert "#0ca30c" in style_delta_cell_value(500)


def test_style_delta_cell_value_negative_is_negative_color() -> None:
    assert "#d03b3b" in style_delta_cell_value(-500)


def test_style_delta_cell_value_zero_has_no_color() -> None:
    assert style_delta_cell_value(0) == ""


def test_style_delta_cell_value_none_has_no_color() -> None:
    assert style_delta_cell_value(None) == ""


def test_style_delta_cell_value_nan_has_no_color() -> None:
    assert style_delta_cell_value(float("nan")) == ""


# ── build_kpi_table ───────────────────────────────────────────────────────────


@pytest.fixture
def fixture_report() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "category": ["beauty", "electronics"],
            "unit_sales_MAT": [1_500, 300],
            "unit_sales_MAT_ya": [1_300, 350],
            "unit_sales_MAT_delta_abs": [200, -50],
            "unit_sales_MAT_delta_pct": [15.38, -14.29],
            "unit_sales_YTD": [800, 150],
            "unit_sales_YTD_ya": [700, 150],
            "unit_sales_YTD_delta_abs": [100, 0],
            "unit_sales_YTD_delta_pct": [14.29, 0.0],
            "dollar_sales_MAT": [45_000.0, 9_000.0],
            "dollar_sales_MAT_ya": [40_000.0, 10_000.0],
            "dollar_sales_MAT_delta_abs": [5_000.0, -1_000.0],
            "dollar_sales_MAT_delta_pct": [12.5, -10.0],
            "dollar_sales_YTD": [20_000.0, 4_000.0],
            "dollar_sales_YTD_ya": [18_000.0, 0.0],
            "dollar_sales_YTD_delta_abs": [2_000.0, None],
            "dollar_sales_YTD_delta_pct": [11.1, None],
        }
    )


def test_build_kpi_table_has_expected_columns(fixture_report: pd.DataFrame) -> None:
    table = build_kpi_table(fixture_report, "unit_sales")
    assert list(table.columns) == [
        "Category", "MAT", "MAT YA", "Δ MAT (abs)", "Δ MAT (%)",
        "YTD", "YTD YA", "Δ YTD (abs)", "Δ YTD (%)",
    ]


def test_build_kpi_table_sorted_alphabetically_by_category(fixture_report: pd.DataFrame) -> None:
    table = build_kpi_table(fixture_report, "unit_sales")
    assert list(table["Category"]) == ["beauty", "electronics"]


def test_build_kpi_table_one_row_per_category(fixture_report: pd.DataFrame) -> None:
    table = build_kpi_table(fixture_report, "unit_sales")
    assert len(table) == len(fixture_report)


def test_build_kpi_table_values_stay_numeric_not_preformatted(fixture_report: pd.DataFrame) -> None:
    # The whole point of splitting build_kpi_table/style_kpi_table: st.dataframe's
    # interactive column-sort needs real numbers here, not display strings.
    table = build_kpi_table(fixture_report, "dollar_sales")
    beauty_row = table[table["Category"] == "beauty"].iloc[0]
    assert beauty_row["MAT"] == 45_000.0
    assert beauty_row["MAT YA"] == 40_000.0
    assert beauty_row["Δ MAT (abs)"] == 5_000.0
    assert beauty_row["Δ MAT (%)"] == pytest.approx(12.5)


def test_build_kpi_table_ya_columns_sit_directly_after_their_current_period(
    fixture_report: pd.DataFrame,
) -> None:
    columns = list(build_kpi_table(fixture_report, "unit_sales").columns)
    assert columns.index("MAT YA") == columns.index("MAT") + 1
    assert columns.index("YTD YA") == columns.index("YTD") + 1


def test_build_kpi_table_missing_delta_pct_stays_nan(fixture_report: pd.DataFrame) -> None:
    table = build_kpi_table(fixture_report, "dollar_sales")
    electronics_row = table[table["Category"] == "electronics"].iloc[0]
    assert pd.isna(electronics_row["Δ YTD (%)"])


# ── style_kpi_table ────────────────────────────────────────────────────────────


def test_style_kpi_table_formats_values_for_display(fixture_report: pd.DataFrame) -> None:
    table = build_kpi_table(fixture_report, "dollar_sales")
    html = style_kpi_table(table, "dollar_sales").to_html()
    assert "$45.0K" in html  # beauty MAT
    assert "▲ +$5.0K" in html  # beauty Δ MAT (abs)
    assert "▲ +12.5%" in html  # beauty Δ MAT (%)
    assert "--" in html  # electronics Δ YTD (abs)/(%): missing year-ago data


def test_style_kpi_table_colors_positive_and_negative_deltas(fixture_report: pd.DataFrame) -> None:
    table = build_kpi_table(fixture_report, "dollar_sales")
    html = style_kpi_table(table, "dollar_sales").to_html()
    assert "#0ca30c" in html  # beauty's positive MAT delta
    assert "#d03b3b" in html  # electronics's negative MAT delta


def test_kpi_table_sorts_numerically_not_lexicographically_by_delta_pct() -> None:
    # Regression test: a prior version of build_kpi_table returned
    # pre-formatted "▲ +763.0%"/"▼ -3.0%" strings. Sorting those as text put
    # every "▼" (down-arrow) row ahead of every "▲" (up-arrow) row, since
    # U+25BC > U+25B2 in Unicode -- so a -3.0% row would "sort descending"
    # ahead of a +763.0% row. The fix keeps the column numeric so a real
    # numeric sort (as st.dataframe's interactive header-click performs)
    # correctly ranks the larger delta first.
    report = pd.DataFrame(
        {
            "category": ["a", "b", "c"],
            "unit_sales_MAT": [100, 100, 100],
            "unit_sales_MAT_ya": [100, 100, 100],
            "unit_sales_MAT_delta_abs": [0, 0, 0],
            "unit_sales_MAT_delta_pct": [-3.0, 763.0, 15.0],
            "unit_sales_YTD": [0, 0, 0],
            "unit_sales_YTD_ya": [0, 0, 0],
            "unit_sales_YTD_delta_abs": [0, 0, 0],
            "unit_sales_YTD_delta_pct": [0.0, 0.0, 0.0],
        }
    )
    table = build_kpi_table(report, "unit_sales")
    sorted_desc = table.sort_values("Δ MAT (%)", ascending=False)
    assert list(sorted_desc["Category"]) == ["b", "c", "a"]


# ── seller_checkbox_key / summarize_seller_selection ─────────────────────────


def test_seller_checkbox_key_is_stable_and_state_specific() -> None:
    assert seller_checkbox_key("SP") == "dashboard_seller_state_SP"
    assert seller_checkbox_key("SP") != seller_checkbox_key("RJ")


def test_summarize_seller_selection_all_selected() -> None:
    available = ["RJ", "SP", "MG"]
    assert summarize_seller_selection(["SP", "MG", "RJ"], available) == "All locations"


def test_summarize_seller_selection_none_selected() -> None:
    available = ["RJ", "SP", "MG"]
    assert summarize_seller_selection([], available) == "No locations selected"


def test_summarize_seller_selection_partial() -> None:
    available = ["RJ", "SP", "MG"]
    assert summarize_seller_selection(["SP"], available) == "1 of 3 selected"


# ── resolve_seller_states_filter ─────────────────────────────────────────────


def test_resolve_seller_states_filter_all_selected_collapses_to_none() -> None:
    available = ["RJ", "SP", "MG"]
    assert resolve_seller_states_filter(["SP", "MG", "RJ"], available) is None


def test_resolve_seller_states_filter_partial_selection_passed_through() -> None:
    available = ["RJ", "SP", "MG"]
    result = resolve_seller_states_filter(["SP"], available)
    assert result == ["SP"]


def test_resolve_seller_states_filter_empty_selection_passed_through_not_none() -> None:
    # Nothing ticked is a deliberate "zero locations" input, distinct from
    # "no filter" -- must NOT collapse to None.
    available = ["RJ", "SP", "MG"]
    assert resolve_seller_states_filter([], available) == []


def test_resolve_seller_states_filter_order_independent() -> None:
    available = ["RJ", "SP", "MG"]
    assert resolve_seller_states_filter(["MG", "RJ", "SP"], available) is None


# ── align_weekly_trend ────────────────────────────────────────────────────────


@pytest.fixture
def fixture_weekly_current() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "iso_week": [1, 2, 3],
            "iso_year": [2026, 2026, 2026],
            "unit_sales": [100, 110, 120],
            "volume_sales_kg": [50.0, 55.0, 60.0],
            "dollar_sales": [1_000.0, 1_100.0, 1_200.0],
        }
    )


@pytest.fixture
def fixture_weekly_year_ago() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "iso_week": [1, 2],
            "iso_year": [2025, 2025],
            "unit_sales": [90, 95],
            "volume_sales_kg": [45.0, 47.5],
            "dollar_sales": [900.0, 950.0],
        }
    )


def test_align_weekly_trend_merges_on_iso_week(
    fixture_weekly_current: pd.DataFrame, fixture_weekly_year_ago: pd.DataFrame
) -> None:
    merged = align_weekly_trend(fixture_weekly_current, fixture_weekly_year_ago, "unit_sales")
    assert list(merged.columns) == ["iso_week", "current", "year_ago"]
    assert list(merged["iso_week"]) == [1, 2, 3]


def test_align_weekly_trend_outer_join_leaves_nan_for_missing_week(
    fixture_weekly_current: pd.DataFrame, fixture_weekly_year_ago: pd.DataFrame
) -> None:
    merged = align_weekly_trend(fixture_weekly_current, fixture_weekly_year_ago, "unit_sales")
    week_3_row = merged[merged["iso_week"] == 3].iloc[0]
    assert week_3_row["current"] == 120
    assert pd.isna(week_3_row["year_ago"])


def test_align_weekly_trend_values_line_up_by_week_not_position(
    fixture_weekly_current: pd.DataFrame, fixture_weekly_year_ago: pd.DataFrame
) -> None:
    merged = align_weekly_trend(fixture_weekly_current, fixture_weekly_year_ago, "dollar_sales")
    week_2_row = merged[merged["iso_week"] == 2].iloc[0]
    assert week_2_row["current"] == 1_100.0
    assert week_2_row["year_ago"] == 950.0


# ── build_trend_chart ────────────────────────────────────────────────────────


def test_build_trend_chart_y_axis_uses_thousands_separators() -> None:
    # Readability: every plot's axis/hover numbers get comma thousands
    # separators, not Plotly's bare default (e.g. "20000").
    merged = pd.DataFrame({"iso_week": [1, 2], "current": [12345.0, 15000.0], "year_ago": [11000.0, 14500.0]})
    fig = build_trend_chart(merged, "Dollar Sales")
    assert fig.layout.yaxis.tickformat == ","
    for trace in fig.data:
        assert ":,.2f" in trace.hovertemplate
