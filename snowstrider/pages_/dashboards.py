"""Dashboards page (SNOW-7): deterministic e-commerce KPI table + weekly trend charts.

Wires Streamlit widgets straight onto the already-tested backend in
`dashboards.ecommerce_kpis` (`get_virtual_today`, `list_seller_states`,
`category_kpi_report`, `weekly_trend`) -- there is no LangGraph and no LLM
call anywhere on this page, matching that module's own "no LLM here" design
note. This module owns the formatting/styling/chart-building glue and the
Streamlit widget wiring; it does not reimplement any KPI math.

Every Snowflake-touching call here is cached in `st.session_state` after its
first call per browser session -- Streamlit reruns the whole script on every
widget interaction, and this project runs on a fixed trial credit budget, so
re-querying Snowflake on every measure-filter click would be wasteful. The
cache is split into two tiers (see `_ensure_base_data_loaded` /
`_ensure_filtered_data_loaded`): `dashboard_virtual_today` and
`dashboard_seller_states_available` never depend on the Seller Location
filter and are loaded once per session; `dashboard_kpi_report` and the two
`dashboard_weekly_trend_*` frames depend on it and are invalidated
specifically when the filter selection changes (see `render_page`). A
"Refresh data" button clears every cache tier to force a full recompute.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from snowflake.snowpark import Session

from dashboards.ecommerce_kpis import category_kpi_report, get_virtual_today, list_seller_states, weekly_trend

logger = logging.getLogger(__name__)

# Measure keys match the column-name/measure vocabulary used throughout
# `dashboards.ecommerce_kpis` (`_MEASURES` there) -- kept in sync manually
# since that module is off-limits to modify for this ticket.
_MEASURE_LABELS: dict[str, str] = {
    "unit_sales": "Unit Sales",
    "volume_sales_kg": "Volume Sales",
    "dollar_sales": "Dollar Sales",
}
_MEASURE_KEYS_BY_LABEL = {label: key for key, label in _MEASURE_LABELS.items()}
_DOLLAR_MEASURE = "dollar_sales"

# Validated, colorblind-safe status colors (dataviz skill) -- used exactly
# as given, not substituted with a different green/red.
_POSITIVE_COLOR = "#0ca30c"
_NEGATIVE_COLOR = "#d03b3b"

# Line-chart series colors: purple matches this app's brand/primary color
# (`.streamlit/config.toml`, `charts/render.py`); gray was validated for
# colorblind-safety/contrast against this app's dark background.
_CURRENT_YEAR_COLOR = "#8B5CF6"
_YEAR_AGO_COLOR = "#898781"

_SESSION_KEYS = (
    "dashboard_virtual_today",
    "dashboard_seller_states_available",
    "dashboard_kpi_report",
    "dashboard_weekly_trend_current",
    "dashboard_weekly_trend_year_ago",
)

# Caches that depend on the Seller Location filter selection -- cleared (and
# only these) whenever the selection changes, so switching states doesn't
# force a re-query of `dashboard_virtual_today`/`dashboard_seller_states_available`,
# neither of which depends on it.
_FILTERED_SESSION_KEYS = (
    "dashboard_kpi_report",
    "dashboard_weekly_trend_current",
    "dashboard_weekly_trend_year_ago",
)


# ── Pure formatting helpers (unit tested, no Streamlit/Snowflake) ───────────

def format_compact(value: float) -> str:
    """Format a number compactly: `1,284` / `12.9K` / `1.2M` / `3.4B`.

    Handles negative values (delta columns can be negative) by formatting
    the magnitude and re-attaching a leading `-`. `None`/`NaN` render as
    `"--"` rather than raising or printing "nan".
    """
    if value is None or pd.isna(value):
        return "--"
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"{sign}{magnitude / 1_000_000_000:.1f}B"
    if magnitude >= 1_000_000:
        return f"{sign}{magnitude / 1_000_000:.1f}M"
    if magnitude >= 1_000:
        return f"{sign}{magnitude / 1_000:.1f}K"
    return f"{sign}{magnitude:,.0f}"


def format_measure_value(value: float, measure_key: str) -> str:
    """Format a plain MAT/YTD measure value, `$`-prefixed for the dollar measure."""
    prefix = "$" if measure_key == _DOLLAR_MEASURE else ""
    return f"{prefix}{format_compact(value)}"


def _delta_arrow_and_sign(value: float) -> tuple[str, str]:
    """Pick a ▲/▼/• glyph and a +/-/"" sign for a delta value.

    Zero is treated as flat (`•`, no sign) rather than forced into either
    the positive or negative bucket.
    """
    if value > 0:
        return "▲", "+"
    if value < 0:
        return "▼", "-"
    return "•", ""


def format_delta_abs(value: float, measure_key: str) -> str:
    """Format an absolute delta with a leading ▲/▼/• glyph -- never color alone.

    The glyph is what makes direction readable for color-blind users; the
    accompanying cell color (`style_delta_cell_value`) is a secondary signal,
    not the only one. `$`-prefixed for the dollar measure. `None`/`NaN` -> `"--"`.
    """
    if value is None or pd.isna(value):
        return "--"
    arrow, sign = _delta_arrow_and_sign(value)
    prefix = "$" if measure_key == _DOLLAR_MEASURE else ""
    return f"{arrow} {sign}{prefix}{format_compact(abs(value))}"


def format_delta_pct(value: float) -> str:
    """Format a percent delta with a leading ▲/▼/• glyph. `None`/`NaN` -> `"--"`.

    `None`/`NaN` here means `_safe_pct_delta` in the backend deliberately
    left the percent change undefined (year-ago value was zero or missing) --
    displayed as `"--"`, not a misleading `0%` or `inf%`.
    """
    if value is None or pd.isna(value):
        return "--"
    arrow, sign = _delta_arrow_and_sign(value)
    return f"{arrow} {sign}{abs(value):.1f}%"


def style_delta_cell_value(value: float) -> str:
    """CSS for a raw (numeric) delta value -- positive/negative/zero/missing.

    Operates on the underlying float, not a formatted display string --
    `build_kpi_table` keeps its columns numeric specifically so `st.dataframe`'s
    interactive column-header sort operates on real numbers (see
    `style_kpi_table`'s docstring for why). Green (positive/better-than-year-ago),
    red (negative/worse), no color for flat (0) or missing (`None`/`NaN`).
    """
    if value is None or pd.isna(value):
        return ""
    if value > 0:
        return f"color: {_POSITIVE_COLOR}; font-weight: 600"
    if value < 0:
        return f"color: {_NEGATIVE_COLOR}; font-weight: 600"
    return ""


def build_kpi_table(report: pd.DataFrame, measure_key: str) -> pd.DataFrame:
    """Build the one-row-per-category KPI table for one measure, values left numeric.

    Reads the `{measure}_MAT`/`{measure}_MAT_ya`/`{measure}_MAT_delta_abs`/
    `{measure}_MAT_delta_pct` (and `_YTD` equivalents) columns produced by
    `category_kpi_report` and renames them to their display headers --
    `MAT`/`MAT YA`/`Δ MAT (abs)`/`Δ MAT (%)` etc. -- without formatting the
    values to display strings (see `style_kpi_table` for that). Sorted
    alphabetically by category for a stable, scannable row order across
    reruns/measure-filter changes.

    Both the current and year-ago raw values are shown (not just the delta)
    so the delta math is independently verifiable at a glance instead of
    needing to be reverse-engineered from `MAT` and `Δ MAT (abs)` alone.
    """
    mat_col = f"{measure_key}_MAT"
    mat_ya_col = f"{mat_col}_ya"
    mat_delta_abs_col = f"{mat_col}_delta_abs"
    mat_delta_pct_col = f"{mat_col}_delta_pct"
    ytd_col = f"{measure_key}_YTD"
    ytd_ya_col = f"{ytd_col}_ya"
    ytd_delta_abs_col = f"{ytd_col}_delta_abs"
    ytd_delta_pct_col = f"{ytd_col}_delta_pct"

    table = pd.DataFrame(
        {
            "Category": report["category"],
            "MAT": report[mat_col],
            "MAT YA": report[mat_ya_col],
            "Δ MAT (abs)": report[mat_delta_abs_col],
            "Δ MAT (%)": report[mat_delta_pct_col],
            "YTD": report[ytd_col],
            "YTD YA": report[ytd_ya_col],
            "Δ YTD (abs)": report[ytd_delta_abs_col],
            "Δ YTD (%)": report[ytd_delta_pct_col],
        }
    )
    return table.sort_values("Category").reset_index(drop=True)


_VALUE_COLUMNS = ("MAT", "MAT YA", "YTD", "YTD YA")
_ABS_DELTA_COLUMNS = ("Δ MAT (abs)", "Δ YTD (abs)")
_PCT_DELTA_COLUMNS = ("Δ MAT (%)", "Δ YTD (%)")


def style_kpi_table(table: pd.DataFrame, measure_key: str):
    """Apply display formatting and delta-cell coloring to a `build_kpi_table` result.

    Kept separate from `build_kpi_table` so the DataFrame handed to
    `st.dataframe` stays numeric end to end -- `st.dataframe`'s interactive
    column-header sort operates on the DataFrame's actual dtype, not on a
    Styler's `.format()` output. Pre-formatting values to display strings (an
    earlier version of this table did) made "sort descending" a lexicographic
    *string* sort instead of a numeric one: the down-arrow glyph `▼` sorts
    after the up-arrow glyph `▲` in Unicode, so every negative delta would
    sort ahead of every positive one regardless of magnitude (a `-3.0%` row
    would out-rank a `+763.0%` row). Returns a `pandas.io.formats.style.Styler`.
    """
    formatters = {col: (lambda v: format_measure_value(v, measure_key)) for col in _VALUE_COLUMNS}
    formatters.update({col: (lambda v: format_delta_abs(v, measure_key)) for col in _ABS_DELTA_COLUMNS})
    formatters.update({col: format_delta_pct for col in _PCT_DELTA_COLUMNS})

    delta_cols = list(_ABS_DELTA_COLUMNS) + list(_PCT_DELTA_COLUMNS)
    return table.style.format(formatters).map(style_delta_cell_value, subset=delta_cols)


def align_weekly_trend(current_df: pd.DataFrame, year_ago_df: pd.DataFrame, measure_key: str) -> pd.DataFrame:
    """Align this-year and year-ago `weekly_trend` results on ISO week-of-year.

    Merges on `iso_week` (not `iso_year` -- the two MAT windows span
    different calendar years by design, e.g. a window ending Aug 2026 vs one
    ending Aug 2025) so week N this year lines up with week N a year ago on
    a shared x-axis. Outer-joins so a week present in only one series (e.g.
    the current MAT window hasn't reached this ISO week yet) still gets a
    row, with the missing side left as `NaN` so Plotly draws a gap rather
    than a false zero.

    Returns:
        A DataFrame with columns `iso_week`, `current`, `year_ago`, sorted
        by `iso_week`.
    """
    current = current_df[["iso_week", measure_key]].rename(columns={measure_key: "current"})
    year_ago = year_ago_df[["iso_week", measure_key]].rename(columns={measure_key: "year_ago"})
    merged = current.merge(year_ago, on="iso_week", how="outer")
    return merged.sort_values("iso_week").reset_index(drop=True)


def seller_checkbox_key(state: str) -> str:
    """`st.session_state` key for one state's checkbox inside the Seller Location popover."""
    return f"dashboard_seller_state_{state}"


def summarize_seller_selection(selected_states: list[str], available_states: list[str]) -> str:
    """One-line summary for the Seller Location popover's collapsed button label."""
    if set(selected_states) == set(available_states):
        return "All locations"
    if not selected_states:
        return "No locations selected"
    return f"{len(selected_states)} of {len(available_states)} selected"


def resolve_seller_states_filter(
    selected_states: list[str], available_states: list[str]
) -> Optional[list[str]]:
    """Collapse a Seller Location multiselect's value into the backend's filter argument.

    "Every available state ticked" collapses to `None` -- the backend's own
    "no filter" sentinel -- so the common (unfiltered) case runs the exact
    same query it always has, rather than a functionally-identical
    `IN (...)` over every known state. Any other selection (including an
    empty one) is passed through as-is; `category_totals`/`weekly_trend`
    treat an empty sequence as "zero locations selected" (a valid, distinct
    input from "no filter").
    """
    if set(selected_states) == set(available_states):
        return None
    return selected_states


def build_trend_chart(merged: pd.DataFrame, title: str) -> go.Figure:
    """Build a 2-line Plotly figure (this year vs. year-ago) over ISO week-of-year.

    `merged` is expected to have `iso_week`/`current`/`year_ago` columns, as
    produced by `align_weekly_trend`. Always exactly two traces so both show
    up in the legend (Plotly's default click-to-toggle needs no extra code).
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=merged["iso_week"], y=merged["current"], mode="lines+markers",
            name="This Year", line=dict(color=_CURRENT_YEAR_COLOR),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=merged["iso_week"], y=merged["year_ago"], mode="lines+markers",
            name="Year Ago", line=dict(color=_YEAR_AGO_COLOR),
        )
    )
    fig.update_layout(
        template="plotly_dark", title=title, xaxis_title="ISO Week", yaxis_title=title,
        margin=dict(t=60, b=40),
    )
    return fig


# ── Streamlit wiring ─────────────────────────────────────────────────────────

def _ensure_base_data_loaded(session: Session) -> bool:
    """Populate `dashboard_virtual_today` and `dashboard_seller_states_available` on first visit.

    Split out from `_ensure_filtered_data_loaded` because neither of these
    depends on the Seller Location filter selection -- they shouldn't be
    re-queried just because the user ticks a different set of states.

    Returns `False` (after already rendering an error) if any Snowflake call
    fails, so `render_page` can bail out early instead of rendering widgets
    against half-loaded data.
    """
    try:
        if "dashboard_virtual_today" not in st.session_state:
            with st.spinner("Determining dashboard 'today'..."):
                st.session_state["dashboard_virtual_today"] = get_virtual_today(session)

        if "dashboard_seller_states_available" not in st.session_state:
            with st.spinner("Loading seller locations..."):
                st.session_state["dashboard_seller_states_available"] = list_seller_states(session)
    except Exception as exc:  # noqa: BLE001 -- last-resort guard so a raw stack trace never reaches the UI
        logger.exception("dashboards: failed to load base dashboard data")
        st.error(f"Could not load dashboard data: {exc}")
        return False

    return True


def _ensure_filtered_data_loaded(session: Session, seller_states: Optional[list[str]]) -> bool:
    """Populate the three seller-location-filtered `dashboard_*` caches if missing.

    Caller (`render_page`) is responsible for clearing `_FILTERED_SESSION_KEYS`
    first when the filter selection has changed since the last rerun -- this
    function only fills in whatever's currently absent from session state.
    """
    virtual_today = st.session_state["dashboard_virtual_today"]

    try:
        if "dashboard_kpi_report" not in st.session_state:
            with st.spinner("Loading category KPIs..."):
                st.session_state["dashboard_kpi_report"] = category_kpi_report(
                    session, virtual_today, seller_states
                )

        if "dashboard_weekly_trend_current" not in st.session_state:
            with st.spinner("Loading weekly trend (this year)..."):
                st.session_state["dashboard_weekly_trend_current"] = weekly_trend(
                    session, virtual_today, years_back=0, seller_states=seller_states
                )

        if "dashboard_weekly_trend_year_ago" not in st.session_state:
            with st.spinner("Loading weekly trend (year ago)..."):
                st.session_state["dashboard_weekly_trend_year_ago"] = weekly_trend(
                    session, virtual_today, years_back=1, seller_states=seller_states
                )
    except Exception as exc:  # noqa: BLE001 -- last-resort guard so a raw stack trace never reaches the UI
        logger.exception("dashboards: failed to load filtered dashboard data")
        st.error(f"Could not load dashboard data: {exc}")
        return False

    return True


def render_page() -> None:
    """Render the Dashboards page: measure-filtered KPI table + weekly trend charts.

    Assumes `st.session_state["snowflake_session"]` is already populated by
    `app.py`'s login flow -- this page is only reachable once logged in.
    """
    st.title("Dashboards")
    st.caption(
        "Deterministic e-commerce KPIs over OLIST.RAW -- period-over-period sales, "
        "no LLM involved on this page."
    )

    session = st.session_state["snowflake_session"]

    if st.button("Refresh data"):
        for key in _SESSION_KEYS:
            st.session_state.pop(key, None)

    if not _ensure_base_data_loaded(session):
        return

    available_states = st.session_state["dashboard_seller_states_available"]
    for state in available_states:
        st.session_state.setdefault(seller_checkbox_key(state), True)
    selected_states = [s for s in available_states if st.session_state[seller_checkbox_key(s)]]

    st.divider()
    with st.popover(f"Seller Location: {summarize_seller_selection(selected_states, available_states)}"):
        st.caption(
            "Restrict every KPI and chart on this page to orders shipped by "
            "sellers in the ticked states. Defaults to all locations."
        )
        select_all_col, clear_all_col = st.columns(2)
        # `st.rerun()` after these two (not needed for individual checkbox
        # ticks -- Streamlit already applies a widget's new value to
        # `session_state` before the script reruns) -- without it, the
        # popover's own collapsed-button label above was already rendered
        # with the pre-click selection and wouldn't reflect "Select all"/
        # "Clear all" until some later, unrelated rerun.
        if select_all_col.button("Select all", use_container_width=True):
            for state in available_states:
                st.session_state[seller_checkbox_key(state)] = True
            st.rerun()
        if clear_all_col.button("Clear all", use_container_width=True):
            for state in available_states:
                st.session_state[seller_checkbox_key(state)] = False
            st.rerun()
        st.divider()
        checkbox_columns = st.columns(3)
        for i, state in enumerate(available_states):
            checkbox_columns[i % 3].checkbox(state, key=seller_checkbox_key(state))

    seller_states_filter = resolve_seller_states_filter(selected_states, available_states)

    # Compare by an order-independent key -- robust regardless of how
    # `selected_states` was ordered.
    applied_key = None if seller_states_filter is None else frozenset(seller_states_filter)
    if st.session_state.get("dashboard_seller_states_applied_key") != applied_key:
        for key in _FILTERED_SESSION_KEYS:
            st.session_state.pop(key, None)
        st.session_state["dashboard_seller_states_applied_key"] = applied_key

    if not _ensure_filtered_data_loaded(session, seller_states_filter):
        return

    report = st.session_state["dashboard_kpi_report"]
    weekly_current = st.session_state["dashboard_weekly_trend_current"]
    weekly_year_ago = st.session_state["dashboard_weekly_trend_year_ago"]

    st.caption(f"Dashboard 'today': {st.session_state['dashboard_virtual_today']}")

    st.divider()
    st.subheader("Category KPIs")
    measure_label = st.selectbox("Measure", list(_MEASURE_LABELS.values()))
    measure_key = _MEASURE_KEYS_BY_LABEL[measure_label]

    table = build_kpi_table(report, measure_key)
    styled_table = style_kpi_table(table, measure_key)
    st.dataframe(styled_table, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Weekly Trend -- This Year vs. Year Ago")
    st.caption("X-axis is ISO week-of-year, so the two lines stay aligned regardless of calendar year.")
    for measure_key_iter, title in _MEASURE_LABELS.items():
        merged = align_weekly_trend(weekly_current, weekly_year_ago, measure_key_iter)
        fig = build_trend_chart(merged, title)
        st.plotly_chart(fig, use_container_width=True)
