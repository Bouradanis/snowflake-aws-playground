"""Fulfillment Performance dashboard backend: period-over-period delivery/ops KPIs.

Same design as `dashboards.ecommerce_kpis` (deterministic BI logic, no
LangGraph/LLM anywhere in this module) but sliced for an operations audience
instead of a commercial one: on-time delivery rate, delivery lead time, and
freight cost ratio, plus a per-seller fulfillment ranking. Reuses
`get_virtual_today`/`mat_window`/`ytd_window`/`list_seller_states`/
`_seller_state_filter_clause`/`_safe_pct_delta` from `ecommerce_kpis` rather
than duplicating them -- the "virtual today" and Seller Location filter
concepts are dashboard-wide, not category-KPI-specific.

Bind-parameter note: same qmark (`?`) positional style as `ecommerce_kpis`,
see that module's docstring for why.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Sequence

import pandas as pd
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException

from dashboards.ecommerce_kpis import (
    _safe_pct_delta,
    _seller_state_filter_clause,
    mat_window,
    ytd_window,
)

logger = logging.getLogger(__name__)

# ── SQL ──────────────────────────────────────────────────────────────────────

# Shared FROM/JOIN/WHERE for all three queries below -- order-item grain
# (an order with items from multiple sellers/categories contributes one row
# per item, matching `ecommerce_kpis._FROM_JOIN_WHERE_SQL`'s convention).
_FROM_JOIN_WHERE_SQL = """\
FROM OLIST.RAW.ORDER_ITEMS oi
JOIN OLIST.RAW.ORDERS o ON oi.order_id = o.order_id
JOIN OLIST.RAW.SELLERS s ON oi.seller_id = s.seller_id
WHERE o.order_approved_at >= ? AND o.order_approved_at < ?"""

# Conditional aggregates shared by fulfillment_totals, seller_fulfillment_ranking,
# and weekly_on_time_trend -- raw counts/sums, not pre-divided ratios, so the
# caller can compute on_time_rate/avg_lead_time_days via `_safe_ratio` and
# never risk a SQL-side divide-by-zero.
_ONTIME_AGG_COLUMNS_SQL = """\
    COUNT(oi.order_item_id) AS item_count,
    SUM(CASE WHEN o.order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END) AS delivered_item_count,
    SUM(CASE WHEN o.order_delivered_customer_date IS NOT NULL
             AND o.order_delivered_customer_date <= o.order_estimated_delivery_date
             THEN 1 ELSE 0 END) AS on_time_item_count,
    SUM(CASE WHEN o.order_delivered_customer_date IS NOT NULL
             THEN DATEDIFF('day', o.order_approved_at, o.order_delivered_customer_date)
             ELSE 0 END) AS total_lead_time_days"""


def _fulfillment_totals_sql(filter_clause: str) -> str:
    return f"""\
SELECT
{_ONTIME_AGG_COLUMNS_SQL},
    SUM(oi.freight_value) AS total_freight,
    SUM(oi.price)         AS total_price
{_FROM_JOIN_WHERE_SQL}{filter_clause}
"""


def _seller_fulfillment_ranking_sql(filter_clause: str) -> str:
    return f"""\
SELECT
    s.seller_id    AS seller_id,
    s.seller_state AS seller_state,
{_ONTIME_AGG_COLUMNS_SQL}
{_FROM_JOIN_WHERE_SQL}{filter_clause}
GROUP BY s.seller_id, s.seller_state
"""


def _weekly_on_time_trend_sql(filter_clause: str) -> str:
    return f"""\
SELECT
    WEEKISO(o.order_approved_at)       AS iso_week,
    YEAROFWEEKISO(o.order_approved_at) AS iso_year,
{_ONTIME_AGG_COLUMNS_SQL}
{_FROM_JOIN_WHERE_SQL}{filter_clause}
GROUP BY iso_year, iso_week
ORDER BY iso_year, iso_week
"""


# ── Pure helpers (no Snowflake/network) ──────────────────────────────────────


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """`numerator / denominator`, or `None` if the denominator is zero/missing.

    Never raises, never divides by zero. `numerator`/`denominator` may be
    `None` (Snowflake `SUM()` over an all-NULL/empty set) rather than `NaN`.
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _safe_abs_delta(current: Optional[float], year_ago: Optional[float]) -> Optional[float]:
    """`current - year_ago`, or `None` if either side is undefined (see `_safe_ratio`)."""
    if current is None or year_ago is None:
        return None
    return current - year_ago


_EMPTY_TOTALS_KEYS = (
    "item_count",
    "delivered_item_count",
    "on_time_item_count",
    "total_lead_time_days",
    "total_freight",
    "total_price",
    "on_time_rate",
    "avg_lead_time_days",
    "freight_ratio",
)


def _empty_fulfillment_totals() -> dict:
    """Zeroed/`None` totals dict for the "zero seller locations selected" short-circuit."""
    zeroed = dict.fromkeys(_EMPTY_TOTALS_KEYS[:6], 0)
    zeroed.update(dict.fromkeys(_EMPTY_TOTALS_KEYS[6:], None))
    return zeroed


# ── fulfillment_totals ────────────────────────────────────────────────────────


def fulfillment_totals(
    session: Session,
    start_date: date,
    end_date: date,
    seller_states: Optional[Sequence[str]] = None,
) -> dict:
    """On-time delivery rate, avg delivery lead time, and freight cost ratio for `[start_date, end_date)`.

    Only order items whose order has a non-NULL `order_delivered_customer_date`
    count toward `on_time_rate`/`avg_lead_time_days` -- undelivered/in-transit
    orders are excluded from those two measures (not treated as late), but
    still count toward `item_count` and `freight_ratio` (freight is charged
    regardless of delivery status).

    Args:
        session: an open Snowpark `Session`.
        start_date: inclusive window start.
        end_date: exclusive window end.
        seller_states: see `ecommerce_kpis.category_totals` -- same semantics.

    Returns:
        A dict with raw counts/sums (`item_count`, `delivered_item_count`,
        `on_time_item_count`, `total_lead_time_days`, `total_freight`,
        `total_price`) and derived ratios (`on_time_rate`,
        `avg_lead_time_days`, `freight_ratio`), each `None` if its
        denominator is zero (e.g. no delivered orders in the window).

    Raises:
        ValueError: if `end_date` is before `start_date`.
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            fails against Snowflake.
    """
    if end_date < start_date:
        raise ValueError(f"end_date ({end_date}) must not be before start_date ({start_date})")

    if seller_states is not None and len(seller_states) == 0:
        return _empty_fulfillment_totals()

    filter_clause, filter_params = _seller_state_filter_clause(seller_states)

    logger.info(
        "fulfillment_totals: querying window [%s, %s), seller_states=%s", start_date, end_date, seller_states
    )
    try:
        row = session.sql(
            _fulfillment_totals_sql(filter_clause), params=[start_date, end_date] + filter_params
        ).collect()[0]
    except SnowparkSQLException as exc:
        logger.error("fulfillment_totals: query failed: %s", exc)
        raise

    # `Session.sql(...).collect()` returns Snowflake NUMBER columns as
    # `decimal.Decimal`, not `float` (unlike `.to_pandas()`, which normalizes
    # to float64) -- cast explicitly here so every downstream ratio/delta
    # computation (including `ecommerce_kpis._safe_pct_delta`'s `* 100.0`,
    # which raises `TypeError` on a bare Decimal) works with plain floats.
    item_count = int(row[0] or 0)
    delivered_item_count = int(row[1] or 0)
    on_time_item_count = int(row[2] or 0)
    total_lead_time_days = float(row[3]) if row[3] is not None else 0.0
    total_freight = float(row[4]) if row[4] is not None else 0.0
    total_price = float(row[5]) if row[5] is not None else 0.0

    return {
        "item_count": item_count,
        "delivered_item_count": delivered_item_count,
        "on_time_item_count": on_time_item_count,
        "total_lead_time_days": total_lead_time_days,
        "total_freight": total_freight,
        "total_price": total_price,
        "on_time_rate": _safe_ratio(on_time_item_count, delivered_item_count),
        "avg_lead_time_days": _safe_ratio(total_lead_time_days, delivered_item_count),
        "freight_ratio": _safe_ratio(total_freight, total_price),
    }


# ── fulfillment_kpi_report ────────────────────────────────────────────────────

_FULFILLMENT_MEASURES = ("on_time_rate", "avg_lead_time_days", "freight_ratio")
_PERIODS = (("MAT", mat_window), ("YTD", ytd_window))


def fulfillment_kpi_report(
    session: Session, virtual_today: date, seller_states: Optional[Sequence[str]] = None
) -> dict:
    """MAT/MAT-YA/YTD/YTD-YA totals and deltas for on-time rate, lead time, and freight ratio.

    Calls `fulfillment_totals` four times (current and year-ago MAT, current
    and year-ago YTD), mirroring `ecommerce_kpis.category_kpi_report` but
    flat (no per-category grouping, since fulfillment is reported as a
    single overall figure, not split by product category).

    For each measure in `on_time_rate`/`avg_lead_time_days`/`freight_ratio`
    and each period in `MAT`/`YTD`, the report has:

    - `{measure}_{period}`: current value (or `None`, see `fulfillment_totals`)
    - `{measure}_{period}_ya`: year-ago value
    - `{measure}_{period}_delta_abs`: current - year_ago, or `None` if either is `None`
    - `{measure}_{period}_delta_pct`: percent change, or `None`/`NaN` if the
      year-ago value is zero/missing (see `ecommerce_kpis._safe_pct_delta`)

    Args:
        session: an open Snowpark `Session`.
        virtual_today: the dashboard's "today", from `get_virtual_today`.
        seller_states: see `ecommerce_kpis.category_totals` -- same semantics.

    Returns:
        A flat dict with the keys described above (9 measures/periods * 4 keys each).
    """
    report: dict = {}
    for period_name, window_fn in _PERIODS:
        cur_start, cur_end = window_fn(virtual_today, 0)
        ya_start, ya_end = window_fn(virtual_today, 1)

        current = fulfillment_totals(session, cur_start, cur_end, seller_states)
        year_ago = fulfillment_totals(session, ya_start, ya_end, seller_states)

        for measure in _FULFILLMENT_MEASURES:
            cur_val = current[measure]
            ya_val = year_ago[measure]
            report[f"{measure}_{period_name}"] = cur_val
            report[f"{measure}_{period_name}_ya"] = ya_val
            report[f"{measure}_{period_name}_delta_abs"] = _safe_abs_delta(cur_val, ya_val)
            report[f"{measure}_{period_name}_delta_pct"] = _safe_pct_delta(cur_val, ya_val)

    logger.info("fulfillment_kpi_report: built report for virtual_today=%s", virtual_today)
    return report


# ── seller_fulfillment_ranking ────────────────────────────────────────────────

_SELLER_RANKING_COLUMNS = (
    "seller_id",
    "seller_state",
    "item_count",
    "delivered_item_count",
    "on_time_rate",
    "avg_lead_time_days",
)


def seller_fulfillment_ranking(
    session: Session,
    start_date: date,
    end_date: date,
    seller_states: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Per-seller on-time rate and avg delivery lead time for `[start_date, end_date)`.

    Sorted ascending by `on_time_rate` (worst first, `NaN` -- sellers with
    zero delivered items in the window -- sorts last) so the sellers most
    responsible for late deliveries surface at the top of the table.

    Args:
        session: an open Snowpark `Session`.
        start_date: inclusive window start.
        end_date: exclusive window end.
        seller_states: see `ecommerce_kpis.category_totals` -- same semantics.

    Returns:
        A DataFrame with columns `seller_id`, `seller_state`, `item_count`,
        `delivered_item_count`, `on_time_rate`, `avg_lead_time_days` -- one
        row per seller with at least one matching order item in the window.

    Raises:
        ValueError: if `end_date` is before `start_date`.
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            fails against Snowflake.
    """
    if end_date < start_date:
        raise ValueError(f"end_date ({end_date}) must not be before start_date ({start_date})")

    if seller_states is not None and len(seller_states) == 0:
        return pd.DataFrame(columns=list(_SELLER_RANKING_COLUMNS))

    filter_clause, filter_params = _seller_state_filter_clause(seller_states)

    logger.info(
        "seller_fulfillment_ranking: querying window [%s, %s), seller_states=%s",
        start_date, end_date, seller_states,
    )
    try:
        df = session.sql(
            _seller_fulfillment_ranking_sql(filter_clause), params=[start_date, end_date] + filter_params
        ).to_pandas()
    except SnowparkSQLException as exc:
        logger.error("seller_fulfillment_ranking: query failed: %s", exc)
        raise

    df.columns = df.columns.str.lower()
    df["on_time_rate"] = [
        _safe_ratio(on_time, delivered)
        for on_time, delivered in zip(df["on_time_item_count"], df["delivered_item_count"])
    ]
    df["avg_lead_time_days"] = [
        _safe_ratio(total_days, delivered)
        for total_days, delivered in zip(df["total_lead_time_days"], df["delivered_item_count"])
    ]
    df = df[list(_SELLER_RANKING_COLUMNS)]
    return df.sort_values("on_time_rate", ascending=True, na_position="last").reset_index(drop=True)


# ── weekly_on_time_trend ───────────────────────────────────────────────────────

_WEEKLY_TREND_COLUMNS = ("iso_week", "iso_year", "on_time_rate", "avg_lead_time_days")


def weekly_on_time_trend(
    session: Session,
    virtual_today: date,
    years_back: int = 0,
    seller_states: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """ISO-week-of-year on-time rate / avg lead time trend over the MAT window `years_back` years back.

    Mirrors `ecommerce_kpis.weekly_trend`'s grain and window (`mat_window`,
    `WEEKISO`/`YEAROFWEEKISO`), but aggregates ratios per week rather than a
    sales measure. Ratios are computed from raw per-week counts (never an
    average of pre-divided per-order-item rates), so a week's `on_time_rate`
    is always a true weighted rate, not skewed by weeks with few orders.

    Args:
        session: an open Snowpark `Session`.
        virtual_today: the dashboard's "today", from `get_virtual_today`.
        years_back: how many years back to shift the MAT window; must be >= 0.
        seller_states: see `ecommerce_kpis.category_totals` -- same semantics.

    Returns:
        A DataFrame with columns `iso_week`, `iso_year`, `on_time_rate`,
        `avg_lead_time_days`, sorted by `(iso_year, iso_week)`.

    Raises:
        ValueError: if `years_back` is negative.
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            fails against Snowflake.
    """
    start_date, end_date = mat_window(virtual_today, years_back)

    if seller_states is not None and len(seller_states) == 0:
        return pd.DataFrame(columns=list(_WEEKLY_TREND_COLUMNS))

    filter_clause, filter_params = _seller_state_filter_clause(seller_states)

    logger.info(
        "weekly_on_time_trend: years_back=%d window=[%s, %s), seller_states=%s",
        years_back, start_date, end_date, seller_states,
    )
    try:
        df = session.sql(
            _weekly_on_time_trend_sql(filter_clause), params=[start_date, end_date] + filter_params
        ).to_pandas()
    except SnowparkSQLException as exc:
        logger.error("weekly_on_time_trend: query failed: %s", exc)
        raise

    df.columns = df.columns.str.lower()
    df["on_time_rate"] = [
        _safe_ratio(on_time, delivered)
        for on_time, delivered in zip(df["on_time_item_count"], df["delivered_item_count"])
    ]
    df["avg_lead_time_days"] = [
        _safe_ratio(total_days, delivered)
        for total_days, delivered in zip(df["total_lead_time_days"], df["delivered_item_count"])
    ]
    return df[list(_WEEKLY_TREND_COLUMNS)]
