"""E-commerce KPI dashboard backend (SNOW-7): period-over-period sales KPIs.

Deterministic BI/reporting logic only -- hand-built SQL + Python date math.
There is deliberately NO LangGraph and NO LLM call anywhere in this module
(contrast with `snowstrider.graph`, the NL-to-SQL pipeline): every query
here is fixed at import time, so there's nothing for `sql_guard` to validate
either. This module has no `streamlit` import and produces no UI -- it is
the data/logic layer a separate Streamlit page consumes.

Bind-parameter note: `Session.sql()` in `snowflake-snowpark-python` only
supports **qmark** (`?`) positional bind variables via its `params` sequence
argument -- there is no `%(name)s` named-parameter form (that's the
`snowflake-connector-python` DB-API style, not what Snowpark's `Session.sql`
exposes). All queries below use `?` placeholders with a positionally-ordered
`params` list, confirmed against the installed `Session.sql` signature/
docstring rather than assumed.

"Virtual today" design note: `get_virtual_today` returns `MAX(order_approved_at)
+ 1 day`, not the max date itself. Every window function below (`mat_window`,
`ytd_window`) treats its `today` argument as the *inclusive* end of a window
conceptually, but `category_totals`/`weekly_trend` implement that with an
*exclusive* upper bound (`order_approved_at < end_date`) for a clean half-open
interval. Because `virtual_today` is one day past the last real order, the
exclusive bound at `virtual_today`'s midnight still captures every order
approved on the actual last day of data -- the `+ 1 day` offset is what makes
the exclusive-bound SQL and the inclusive-window English line up.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

import pandas as pd
from dateutil.relativedelta import relativedelta
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException

logger = logging.getLogger(__name__)

# ── SQL ──────────────────────────────────────────────────────────────────────

_MAX_ORDER_APPROVED_AT_SQL = "SELECT MAX(order_approved_at) AS max_approved_at FROM OLIST.RAW.ORDERS"

# Shared FROM/JOIN/WHERE clause for the two per-order-item aggregate queries
# below -- both category_totals and weekly_trend aggregate the exact same
# join of ORDER_ITEMS -> ORDERS -> PRODUCTS -> PRODUCT_CATEGORY_NAME_TRANSLATION,
# plus SELLERS (for the Seller Location filter), over a `[start_date, end_date)`
# window, differing only in the GROUP BY.
_FROM_JOIN_WHERE_SQL = """\
FROM OLIST.RAW.ORDER_ITEMS oi
JOIN OLIST.RAW.ORDERS o ON oi.order_id = o.order_id
JOIN OLIST.RAW.PRODUCTS p ON oi.product_id = p.product_id
JOIN OLIST.RAW.PRODUCT_CATEGORY_NAME_TRANSLATION pt
    ON p.product_category_name = pt.product_category_name
JOIN OLIST.RAW.SELLERS s ON oi.seller_id = s.seller_id
WHERE o.order_approved_at >= ? AND o.order_approved_at < ?
  AND o.order_status NOT IN ('canceled', 'unavailable')"""

_LIST_SELLER_STATES_SQL = (
    "SELECT DISTINCT seller_state FROM OLIST.RAW.SELLERS "
    "WHERE seller_state IS NOT NULL ORDER BY seller_state"
)


def _seller_state_filter_clause(seller_states: Optional[Sequence[str]]) -> tuple[str, list]:
    """Build an ` AND s.seller_state IN (?, ...)` clause plus its bind params.

    `None` means no filter (every seller location included) -- the resulting
    SQL is identical to pre-filter behavior. Callers are responsible for
    short-circuiting an empty sequence themselves *before* calling this (and
    before touching Snowflake at all): `IN ()` is invalid Snowflake SQL, and
    "zero locations selected" should mean "zero rows", not "no filter".
    """
    if seller_states is None:
        return "", []
    placeholders = ", ".join(["?"] * len(seller_states))
    return f" AND s.seller_state IN ({placeholders})", list(seller_states)


def _category_totals_sql(filter_clause: str) -> str:
    return f"""\
SELECT
    pt.product_category_name_english AS category,
    COUNT(oi.order_item_id)          AS unit_sales,
    SUM(p.product_weight_g) / 1000.0 AS volume_sales_kg,
    SUM(oi.price)                    AS dollar_sales
{_FROM_JOIN_WHERE_SQL}{filter_clause}
GROUP BY pt.product_category_name_english
"""


def _weekly_trend_sql(filter_clause: str) -> str:
    return f"""\
SELECT
    WEEKISO(o.order_approved_at)        AS iso_week,
    YEAROFWEEKISO(o.order_approved_at)  AS iso_year,
    COUNT(oi.order_item_id)             AS unit_sales,
    SUM(p.product_weight_g) / 1000.0    AS volume_sales_kg,
    SUM(oi.price)                       AS dollar_sales
{_FROM_JOIN_WHERE_SQL}{filter_clause}
GROUP BY iso_year, iso_week
ORDER BY iso_year, iso_week
"""

# The three measures every window/report function below deals in. Not built
# as a generic/extensible registry on purpose -- the spec is explicit that
# Unit/Volume/Dollar is the full set for this dashboard, no premature
# abstraction for hypothetical future measures.
_MEASURES = ("unit_sales", "volume_sales_kg", "dollar_sales")

# (period label, window function) pairs the KPI report is built from.
_PERIODS = (("MAT", "mat_window"), ("YTD", "ytd_window"))


# ── Virtual "today" ──────────────────────────────────────────────────────────

def get_virtual_today(session: Session) -> date:
    """Return `MAX(order_approved_at) + 1 day` from `OLIST.RAW.ORDERS`.

    This is the one and only place in the KPI dashboard that touches
    Snowflake to determine "what is today" -- the Olist dataset is a
    historical dump with no orders near the real calendar date, so every
    other function in this module takes `today`/`virtual_today` as a plain
    Python `date` argument and does its date math locally, with no further
    network calls.

    Raises:
        RuntimeError: if `OLIST.RAW.ORDERS` is empty or every
            `order_approved_at` is NULL, so `MAX()` returns NULL -- this is
            treated as a hard error rather than silently producing a bogus
            "today" from `None` arithmetic.
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            itself fails against Snowflake.
    """
    logger.info("get_virtual_today: querying MAX(order_approved_at) from OLIST.RAW.ORDERS")
    try:
        rows = session.sql(_MAX_ORDER_APPROVED_AT_SQL).collect()
    except SnowparkSQLException as exc:
        logger.error("get_virtual_today: query failed: %s", exc)
        raise

    if not rows or rows[0][0] is None:
        raise RuntimeError(
            "OLIST.RAW.ORDERS has no non-NULL order_approved_at values "
            "(table is empty or all NULL) -- cannot determine a virtual 'today'."
        )

    max_approved_at = rows[0][0]
    max_date = max_approved_at.date() if isinstance(max_approved_at, datetime) else max_approved_at
    virtual_today = max_date + timedelta(days=1)

    logger.info("get_virtual_today: MAX(order_approved_at)=%s -> virtual_today=%s", max_approved_at, virtual_today)
    return virtual_today


def list_seller_states(session: Session) -> list[str]:
    """Distinct, sorted `SELLERS.seller_state` values -- options for the Seller Location filter.

    Not scoped to any date window or measure -- it's the full set of states
    any seller is registered in, used both as the filter widget's option
    list and its "all selected" default. A state with zero sales in the
    currently-selected KPI window still appears here; it just contributes
    nothing to the totals.

    Raises:
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            fails against Snowflake.
    """
    logger.info("list_seller_states: querying distinct seller_state from OLIST.RAW.SELLERS")
    try:
        rows = session.sql(_LIST_SELLER_STATES_SQL).collect()
    except SnowparkSQLException as exc:
        logger.error("list_seller_states: query failed: %s", exc)
        raise
    return [row[0] for row in rows]


# ── Period-boundary math (pure, no Snowflake/network) ───────────────────────

def _check_years_back(years_back: int) -> None:
    if years_back < 0:
        raise ValueError(f"years_back must be non-negative, got {years_back}")


def mat_window(today: date, years_back: int = 0) -> tuple[date, date]:
    """Moving Annual Total window: 12 months ending at `today`, shifted back `years_back` years.

    `mat_window(today, 0)` is the inclusive 12-month window
    `(today - 1 year + 1 day, today)`. `mat_window(today, N)` is that same
    12-month window shifted back exactly N years -- equivalent to
    `mat_window(today - N years, 0)`.

    Uses `dateutil.relativedelta` (not `timedelta(days=365)`) so leap years
    are handled correctly (e.g. shifting Feb 29 back a year lands on Feb 28,
    not an arbitrary 365-day offset).

    Args:
        today: the inclusive end date of the (unshifted) window.
        years_back: how many years to shift the window back; must be >= 0.

    Returns:
        `(start_date, end_date)`, both inclusive.

    Raises:
        ValueError: if `years_back` is negative.
    """
    _check_years_back(years_back)
    end = today - relativedelta(years=years_back)
    start = end - relativedelta(years=1) + timedelta(days=1)
    return start, end


def ytd_window(today: date, years_back: int = 0) -> tuple[date, date]:
    """Year-to-date window: Jan 1 of `today`'s year through `today`, shifted back `years_back` years.

    `ytd_window(today, 0)` is `(date(today.year, 1, 1), today)`.
    `ytd_window(today, N)` shifts both ends back N years via
    `dateutil.relativedelta` (leap-year safe).

    Args:
        today: the inclusive end date of the (unshifted) window.
        years_back: how many years to shift the window back; must be >= 0.

    Returns:
        `(start_date, end_date)`, both inclusive.

    Raises:
        ValueError: if `years_back` is negative.
    """
    _check_years_back(years_back)
    end = today - relativedelta(years=years_back)
    start = date(end.year, 1, 1)
    return start, end


_WINDOW_FUNCS = {"mat_window": mat_window, "ytd_window": ytd_window}


# ── Category totals ──────────────────────────────────────────────────────────

def category_totals(
    session: Session,
    start_date: date,
    end_date: date,
    seller_states: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Unit/Volume/Dollar sales per product category for `[start_date, end_date)`.

    Excludes `order_status` values `'canceled'` and `'unavailable'` -- those
    never became real transactions, so counting their `price`/weight as
    sales would overstate revenue. Every other status (`delivered`,
    `shipped`, `invoiced`, `processing`, `created`, `approved`) counts,
    including orders still in flight, since "not yet delivered" is
    legitimate pipeline volume, not noise.

    Dates and seller states are passed as Snowpark qmark (`?`) bind
    parameters, never f-string-interpolated into the SQL text.

    Args:
        session: an open Snowpark `Session`.
        start_date: inclusive window start.
        end_date: exclusive window end.
        seller_states: optional `SELLERS.seller_state` values to restrict to
            (the Seller Location filter). `None` (default) means no filter --
            every seller location included, identical to pre-filter
            behavior. An empty sequence is a deliberate "no locations
            selected" input and short-circuits to an empty result without
            querying Snowflake at all.

    Returns:
        A DataFrame with columns `category`, `unit_sales`, `volume_sales_kg`,
        `dollar_sales` -- one row per category with at least one matching
        order item in the window. `start_date == end_date` is a valid
        zero-width window (e.g. `ytd_window(today, 0)` when `today` is Jan 1)
        and simply yields an empty result, not an error -- only an
        *inverted* window is rejected.

    Raises:
        ValueError: if `end_date` is before `start_date`.
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            fails against Snowflake.
    """
    if end_date < start_date:
        raise ValueError(f"end_date ({end_date}) must not be before start_date ({start_date})")

    if seller_states is not None and len(seller_states) == 0:
        return pd.DataFrame(columns=["category", "unit_sales", "volume_sales_kg", "dollar_sales"])

    filter_clause, filter_params = _seller_state_filter_clause(seller_states)

    logger.info(
        "category_totals: querying window [%s, %s), seller_states=%s", start_date, end_date, seller_states
    )
    try:
        df = session.sql(
            _category_totals_sql(filter_clause), params=[start_date, end_date] + filter_params
        ).to_pandas()
    except SnowparkSQLException as exc:
        logger.error("category_totals: query failed: %s", exc)
        raise

    df.columns = df.columns.str.lower()
    return df


# ── Category KPI report ──────────────────────────────────────────────────────

def _rename_measures(df: pd.DataFrame, period: str, suffix: str) -> pd.DataFrame:
    """Rename `unit_sales`/`volume_sales_kg`/`dollar_sales` to `{measure}_{period}{suffix}`."""
    rename_map = {measure: f"{measure}_{period}{suffix}" for measure in _MEASURES}
    return df.rename(columns=rename_map)


def _safe_pct_delta(current: Optional[float], year_ago: Optional[float]) -> Optional[float]:
    """Percent change from `year_ago` to `current`, or `None` if undefined.

    Returns `None` (never raises, never divides by zero) when `year_ago` is
    zero, or when either value is missing/NaN.
    """
    if pd.isna(current) or pd.isna(year_ago) or year_ago == 0:
        return None
    return (current - year_ago) / year_ago * 100.0


def category_kpi_report(
    session: Session, virtual_today: date, seller_states: Optional[Sequence[str]] = None
) -> pd.DataFrame:
    """One row per category with MAT/MAT-YA/YTD/YTD-YA totals and deltas for all three measures.

    Calls `category_totals` four times -- current and year-ago MAT, current
    and year-ago YTD -- and outer-joins all four on `category`, so a
    category that only exists in some of the four windows (e.g. zero sales
    in the year-ago period) still gets a row rather than being dropped;
    missing measure values are treated as 0 sales for that window.

    For each measure in `unit_sales`/`volume_sales_kg`/`dollar_sales` and
    each period in `MAT`/`YTD`, the report has:

    - `{measure}_{period}`: current value
    - `{measure}_{period}_ya`: year-ago value
    - `{measure}_{period}_delta_abs`: current - year_ago
    - `{measure}_{period}_delta_pct`: percent change, or `NaN`/`None` if the
      year-ago value is zero or missing (see `_safe_pct_delta`)

    Args:
        session: an open Snowpark `Session`.
        virtual_today: the dashboard's "today", from `get_virtual_today`.
        seller_states: see `category_totals` -- passed through to all four
            underlying calls, same semantics (`None` = all locations, an
            empty sequence = zero-row result for every window).

    Returns:
        A DataFrame with one row per category and the columns described above.
    """
    frames: list[pd.DataFrame] = []
    for period_name, window_fn_name in _PERIODS:
        window_fn = _WINDOW_FUNCS[window_fn_name]
        cur_start, cur_end = window_fn(virtual_today, 0)
        ya_start, ya_end = window_fn(virtual_today, 1)

        cur_df = _rename_measures(
            category_totals(session, cur_start, cur_end, seller_states), period_name, ""
        )
        ya_df = _rename_measures(
            category_totals(session, ya_start, ya_end, seller_states), period_name, "_ya"
        )
        frames.append(cur_df)
        frames.append(ya_df)

    report = frames[0]
    for frame in frames[1:]:
        report = report.merge(frame, on="category", how="outer")

    measure_cols = [
        f"{measure}_{period_name}{suffix}"
        for period_name, _ in _PERIODS
        for suffix in ("", "_ya")
        for measure in _MEASURES
    ]
    report[measure_cols] = report[measure_cols].fillna(0.0)

    for period_name, _ in _PERIODS:
        for measure in _MEASURES:
            cur_col = f"{measure}_{period_name}"
            ya_col = f"{measure}_{period_name}_ya"
            report[f"{cur_col}_delta_abs"] = report[cur_col] - report[ya_col]
            report[f"{cur_col}_delta_pct"] = [
                _safe_pct_delta(cur, ya) for cur, ya in zip(report[cur_col], report[ya_col])
            ]

    report = report.reset_index(drop=True)
    logger.info("category_kpi_report: built report for %d categories", len(report))
    return report


# ── Weekly trend ──────────────────────────────────────────────────────────────

def weekly_trend(
    session: Session,
    virtual_today: date,
    years_back: int = 0,
    seller_states: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """ISO-week-of-year sales trend over the MAT window `years_back` years back.

    Groups by Snowflake's native `WEEKISO()`/`YEAROFWEEKISO()` (ISO-8601
    week-of-year and the ISO week-year that owns it -- distinct from the
    calendar year for the handful of dates near Dec 31/Jan 1 that ISO 8601
    assigns to the adjacent year's week 1 or week 52/53) directly in SQL,
    over the `mat_window(virtual_today, years_back)` date range.

    The caller (UI layer) is expected to request `years_back=0` and
    `years_back=1` and align the two resulting DataFrames by `iso_week` to
    plot two lines on a common week-of-year x-axis -- this function only
    returns the per-week aggregates, it does not do that alignment itself.

    Args:
        session: an open Snowpark `Session`.
        virtual_today: the dashboard's "today", from `get_virtual_today`.
        years_back: how many years back to shift the MAT window; must be >= 0.
        seller_states: see `category_totals` -- same semantics (`None` = all
            locations, an empty sequence = zero-row result, no query run).

    Returns:
        A DataFrame with columns `iso_week`, `iso_year`, `unit_sales`,
        `volume_sales_kg`, `dollar_sales`, sorted by `(iso_year, iso_week)`.

    Raises:
        ValueError: if `years_back` is negative.
        snowflake.snowpark.exceptions.SnowparkSQLException: if the query
            fails against Snowflake.
    """
    start_date, end_date = mat_window(virtual_today, years_back)

    if seller_states is not None and len(seller_states) == 0:
        return pd.DataFrame(columns=["iso_week", "iso_year", "unit_sales", "volume_sales_kg", "dollar_sales"])

    filter_clause, filter_params = _seller_state_filter_clause(seller_states)

    logger.info(
        "weekly_trend: years_back=%d window=[%s, %s), seller_states=%s",
        years_back, start_date, end_date, seller_states,
    )
    try:
        df = session.sql(
            _weekly_trend_sql(filter_clause), params=[start_date, end_date] + filter_params
        ).to_pandas()
    except SnowparkSQLException as exc:
        logger.error("weekly_trend: query failed: %s", exc)
        raise

    df.columns = df.columns.str.lower()
    return df
