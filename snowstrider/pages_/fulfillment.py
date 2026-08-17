"""Fulfillment Performance page: on-time delivery rate, lead time, and freight cost KPIs.

Operations-audience counterpart to the Dashboards page's Category KPIs
(sales/commercial): on-time delivery rate, delivery lead time, freight cost
ratio, and a per-seller fulfillment ranking, all sliced by the same Seller
Location filter. Wires Streamlit straight onto `dashboards.fulfillment` --
no LangGraph, no LLM call on this page either.

`dashboard_virtual_today` / `dashboard_seller_states_available` and the
Seller Location checkbox state (`seller_checkbox_key`) are shared with
`pages_.dashboards` (same session-state keys, same helper functions,
imported not duplicated) so "today" and the seller list are fetched once no
matter which dashboard page loads first, and the location selection stays
in sync across both pages. This page's *own* filtered caches
(`fulfillment_*`) are tracked and invalidated independently via
`fulfillment_seller_states_applied_key` -- a deliberately separate tracking
key from `pages_.dashboards`'s `dashboard_seller_states_applied_key`, so a
filter change made while on one page can't leave the other page's
already-loaded, differently-filtered caches looking fresh when they're
actually stale.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import streamlit as st
from snowflake.snowpark import Session

from dashboards.ecommerce_kpis import mat_window
from dashboards.fulfillment import fulfillment_kpi_report, seller_fulfillment_ranking, weekly_on_time_trend
from pages_.dashboards import (
    _ensure_base_data_loaded,
    align_weekly_trend,
    build_trend_chart,
    resolve_seller_states_filter,
    seller_checkbox_key,
    summarize_seller_selection,
)

logger = logging.getLogger(__name__)

_FILTERED_SESSION_KEYS = (
    "fulfillment_kpi_report",
    "fulfillment_seller_ranking",
    "fulfillment_weekly_trend_current",
    "fulfillment_weekly_trend_year_ago",
)


# ── Pure formatting helpers (unit tested, no Streamlit/Snowflake) ───────────


def format_rate(value: Optional[float]) -> str:
    """Format a 0-1 rate as a percentage, one decimal. `None`/`NaN` -> `"--"`."""
    if value is None or pd.isna(value):
        return "--"
    return f"{value * 100:.1f}%"


def format_count(value: Optional[float]) -> str:
    """Format an integer count with thousands separators, e.g. `1,234,567`. `None`/`NaN` -> `"--"`."""
    if value is None or pd.isna(value):
        return "--"
    return f"{int(value):,}"


def format_days(value: Optional[float]) -> str:
    """Format a day count, one decimal. `None`/`NaN` -> `"--"`."""
    if value is None or pd.isna(value):
        return "--"
    return f"{value:.1f} days"


def format_delta_pp(value: Optional[float]) -> Optional[str]:
    """Format a 0-1 rate delta as signed percentage points, for `st.metric`'s `delta` arg.

    `None`/`NaN` -> `None` (not `"--"`) -- `st.metric` renders no delta
    indicator at all when `delta=None`, which is the right display for "no
    year-ago data to compare against", vs. a `"--"` string that would render
    as if a delta of literally zero-ish were computed.
    """
    if value is None or pd.isna(value):
        return None
    return f"{value * 100:+.1f} pp"


def format_delta_days(value: Optional[float]) -> Optional[str]:
    """Format a day-count delta, signed, for `st.metric`'s `delta` arg. `None`/`NaN` -> `None`."""
    if value is None or pd.isna(value):
        return None
    return f"{value:+.1f} days"


_SELLER_RANKING_COLUMN_LABELS = {
    "seller_id": "Seller",
    "seller_state": "State",
    "item_count": "Items",
    "delivered_item_count": "Delivered",
    "on_time_rate": "On-Time Rate",
    "avg_lead_time_days": "Avg Lead Time (days)",
}


def build_seller_ranking_table(ranking: pd.DataFrame) -> pd.DataFrame:
    """Rename `seller_fulfillment_ranking`'s columns to their display headers.

    Values are left numeric (not pre-formatted) for the same reason as
    `pages_.dashboards.build_kpi_table`: so `st.dataframe`'s interactive
    column-sort operates on real numbers. Row order (worst on-time rate
    first) is preserved from the backend, not re-sorted here.
    """
    return ranking.rename(columns=_SELLER_RANKING_COLUMN_LABELS)


def style_seller_ranking_table(table: pd.DataFrame):
    """Apply display formatting to a `build_seller_ranking_table` result. Returns a `Styler`."""
    return table.style.format(
        {
            "Items": format_count,
            "Delivered": format_count,
            "On-Time Rate": format_rate,
            "Avg Lead Time (days)": format_days,
        }
    )


# ── Streamlit wiring ─────────────────────────────────────────────────────────


def _ensure_filtered_data_loaded(session: Session, seller_states: Optional[list[str]]) -> bool:
    """Populate this page's filtered `fulfillment_*` caches if missing.

    Caller (`render_page`) is responsible for clearing `_FILTERED_SESSION_KEYS`
    first when the filter selection has changed since this page's data was
    last loaded -- this function only fills in whatever's currently absent.
    """
    virtual_today = st.session_state["dashboard_virtual_today"]

    try:
        if "fulfillment_kpi_report" not in st.session_state:
            with st.spinner("Loading fulfillment KPIs..."):
                st.session_state["fulfillment_kpi_report"] = fulfillment_kpi_report(
                    session, virtual_today, seller_states
                )

        if "fulfillment_seller_ranking" not in st.session_state:
            with st.spinner("Loading seller fulfillment ranking..."):
                mat_start, mat_end = mat_window(virtual_today, 0)
                st.session_state["fulfillment_seller_ranking"] = seller_fulfillment_ranking(
                    session, mat_start, mat_end, seller_states
                )

        if "fulfillment_weekly_trend_current" not in st.session_state:
            with st.spinner("Loading weekly on-time trend (this year)..."):
                st.session_state["fulfillment_weekly_trend_current"] = weekly_on_time_trend(
                    session, virtual_today, years_back=0, seller_states=seller_states
                )

        if "fulfillment_weekly_trend_year_ago" not in st.session_state:
            with st.spinner("Loading weekly on-time trend (year ago)..."):
                st.session_state["fulfillment_weekly_trend_year_ago"] = weekly_on_time_trend(
                    session, virtual_today, years_back=1, seller_states=seller_states
                )
    except Exception as exc:  # noqa: BLE001 -- last-resort guard so a raw stack trace never reaches the UI
        logger.exception("fulfillment: failed to load filtered dashboard data")
        st.error(f"Could not load fulfillment data: {exc}")
        return False

    return True


def render_page() -> None:
    """Render the Fulfillment Performance page: KPI tiles + seller ranking + weekly trend.

    Assumes `st.session_state["snowflake_session"]` is already populated by
    `app.py`'s login flow -- this page is only reachable once logged in.
    """
    st.title("Fulfillment Performance")
    st.caption(
        "Deterministic delivery/ops KPIs over OLIST.RAW -- on-time delivery rate, "
        "lead time, and freight cost, no LLM involved on this page."
    )

    session = st.session_state["snowflake_session"]

    if st.button("Refresh data"):
        for key in _FILTERED_SESSION_KEYS:
            st.session_state.pop(key, None)
        st.session_state.pop("dashboard_virtual_today", None)
        st.session_state.pop("dashboard_seller_states_available", None)

    if not _ensure_base_data_loaded(session):
        return

    available_states = st.session_state["dashboard_seller_states_available"]
    for state in available_states:
        st.session_state.setdefault(seller_checkbox_key(state), True)
    selected_states = [s for s in available_states if st.session_state[seller_checkbox_key(s)]]

    st.divider()
    with st.popover(f"Seller Location: {summarize_seller_selection(selected_states, available_states)}"):
        st.caption(
            "Restrict every KPI, ranking, and chart on this page to orders shipped by "
            "sellers in the ticked states. Shared with the Dashboards page."
        )
        select_all_col, clear_all_col = st.columns(2)
        if select_all_col.button("Select all", use_container_width=True, key="fulfillment_select_all"):
            for state in available_states:
                st.session_state[seller_checkbox_key(state)] = True
            st.rerun()
        if clear_all_col.button("Clear all", use_container_width=True, key="fulfillment_clear_all"):
            for state in available_states:
                st.session_state[seller_checkbox_key(state)] = False
            st.rerun()
        st.divider()
        checkbox_columns = st.columns(3)
        for i, state in enumerate(available_states):
            checkbox_columns[i % 3].checkbox(state, key=seller_checkbox_key(state), help=None)

    seller_states_filter = resolve_seller_states_filter(selected_states, available_states)

    applied_key = None if seller_states_filter is None else frozenset(seller_states_filter)
    if st.session_state.get("fulfillment_seller_states_applied_key") != applied_key:
        for key in _FILTERED_SESSION_KEYS:
            st.session_state.pop(key, None)
        st.session_state["fulfillment_seller_states_applied_key"] = applied_key

    if not _ensure_filtered_data_loaded(session, seller_states_filter):
        return

    report = st.session_state["fulfillment_kpi_report"]
    ranking = st.session_state["fulfillment_seller_ranking"]
    weekly_current = st.session_state["fulfillment_weekly_trend_current"]
    weekly_year_ago = st.session_state["fulfillment_weekly_trend_year_ago"]

    st.caption(f"Dashboard 'today': {st.session_state['dashboard_virtual_today']}")

    st.divider()
    st.subheader("Fulfillment KPIs (MAT vs. Year Ago)")
    tile_cols = st.columns(3)
    tile_cols[0].metric(
        "On-Time Delivery Rate",
        format_rate(report["on_time_rate_MAT"]),
        delta=format_delta_pp(report["on_time_rate_MAT_delta_abs"]),
        delta_color="normal",
    )
    tile_cols[1].metric(
        "Avg Delivery Lead Time",
        format_days(report["avg_lead_time_days_MAT"]),
        delta=format_delta_days(report["avg_lead_time_days_MAT_delta_abs"]),
        delta_color="inverse",
    )
    tile_cols[2].metric(
        "Freight Cost Ratio",
        format_rate(report["freight_ratio_MAT"]),
        delta=format_delta_pp(report["freight_ratio_MAT_delta_abs"]),
        delta_color="inverse",
    )

    st.divider()
    st.subheader("Seller Fulfillment Ranking (MAT, worst on-time rate first)")
    table = build_seller_ranking_table(ranking)
    styled_table = style_seller_ranking_table(table)
    st.dataframe(styled_table, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Weekly On-Time Rate -- This Year vs. Year Ago")
    st.caption("X-axis is ISO week-of-year, so the two lines stay aligned regardless of calendar year.")
    merged = align_weekly_trend(weekly_current, weekly_year_ago, "on_time_rate")
    fig = build_trend_chart(merged, "On-Time Rate")
    st.plotly_chart(fig, use_container_width=True)
