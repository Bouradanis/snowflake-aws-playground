"""Hardcoded allowlist and prompt-context renderer for the OLIST.RAW schema.

This module is the single source of truth for "what tables/columns exist" as
far as Snowstrider is concerned. It is intentionally NOT introspected live
from Snowflake at request time — two reasons:

1. `sql_guard.validator` needs a static allowlist it can check an LLM-written
   query against without a network round-trip (and without trusting whatever
   the LLM claims the schema is).
2. The table/column list is read directly from the DDL in
   `databases/OLIST/RAW/tables/*.sql` (all 9 tables, TRANSIENT), so it is
   byte-accurate to what was actually deployed as of Jira SNOW-3.

If the OLIST.RAW schema changes, this file must be updated by hand to match
the DDL — there is no drift-detection here.
"""

from __future__ import annotations

# Table name -> ordered list of (column_name, snowflake_type) tuples, taken
# verbatim from databases/OLIST/RAW/tables/*.sql.
OLIST_RAW_TABLES: dict[str, list[tuple[str, str]]] = {
    "CUSTOMERS": [
        ("customer_id", "VARCHAR"),
        ("customer_unique_id", "VARCHAR"),
        ("customer_zip_code_prefix", "VARCHAR(5)"),
        ("customer_city", "VARCHAR"),
        ("customer_state", "VARCHAR(2)"),
    ],
    "SELLERS": [
        ("seller_id", "VARCHAR"),
        ("seller_zip_code_prefix", "VARCHAR(5)"),
        ("seller_city", "VARCHAR"),
        ("seller_state", "VARCHAR(2)"),
    ],
    "PRODUCT_CATEGORY_NAME_TRANSLATION": [
        ("product_category_name", "VARCHAR"),
        ("product_category_name_english", "VARCHAR"),
    ],
    "PRODUCTS": [
        ("product_id", "VARCHAR"),
        ("product_category_name", "VARCHAR"),
        ("product_name_lenght", "NUMBER(10,0)"),
        ("product_description_lenght", "NUMBER(10,0)"),
        ("product_photos_qty", "NUMBER(10,0)"),
        ("product_weight_g", "NUMBER(10,0)"),
        ("product_length_cm", "NUMBER(10,0)"),
        ("product_height_cm", "NUMBER(10,0)"),
        ("product_width_cm", "NUMBER(10,0)"),
    ],
    "GEOLOCATION": [
        ("geolocation_zip_code_prefix", "VARCHAR(5)"),
        ("geolocation_lat", "FLOAT"),
        ("geolocation_lng", "FLOAT"),
        ("geolocation_city", "VARCHAR"),
        ("geolocation_state", "VARCHAR(2)"),
    ],
    "ORDERS": [
        ("order_id", "VARCHAR"),
        ("customer_id", "VARCHAR"),
        ("order_status", "VARCHAR(20)"),
        ("order_purchase_timestamp", "TIMESTAMP_NTZ"),
        ("order_approved_at", "TIMESTAMP_NTZ"),
        ("order_delivered_carrier_date", "TIMESTAMP_NTZ"),
        ("order_delivered_customer_date", "TIMESTAMP_NTZ"),
        ("order_estimated_delivery_date", "TIMESTAMP_NTZ"),
    ],
    "ORDER_ITEMS": [
        ("order_id", "VARCHAR"),
        ("order_item_id", "NUMBER(5,0)"),
        ("product_id", "VARCHAR"),
        ("seller_id", "VARCHAR"),
        ("shipping_limit_date", "TIMESTAMP_NTZ"),
        ("price", "NUMBER(10,2)"),
        ("freight_value", "NUMBER(10,2)"),
    ],
    "ORDER_PAYMENTS": [
        ("order_id", "VARCHAR"),
        ("payment_sequential", "NUMBER(3,0)"),
        ("payment_type", "VARCHAR(20)"),
        ("payment_installments", "NUMBER(3,0)"),
        ("payment_value", "NUMBER(10,2)"),
    ],
    "ORDER_REVIEWS": [
        ("review_id", "VARCHAR"),
        ("order_id", "VARCHAR"),
        ("review_score", "NUMBER(1,0)"),
        ("review_comment_title", "VARCHAR"),
        ("review_comment_message", "VARCHAR"),
        ("review_creation_date", "TIMESTAMP_NTZ"),
        ("review_answer_timestamp", "TIMESTAMP_NTZ"),
    ],
}

# Short, high-signal notes per table -- FK relationships and the gotchas
# already documented in the DDL comments (databases/OLIST/RAW/tables/*.sql).
# Kept to 1-2 lines each so the rendered prompt context stays compact.
_TABLE_NOTES: dict[str, str] = {
    "CUSTOMERS": (
        "customer_id is the per-order key (joins ORDERS.customer_id); "
        "customer_unique_id identifies the same real person across repeat orders -- "
        "group by customer_unique_id for 'unique customers', not customer_id."
    ),
    "SELLERS": "seller_id joins ORDER_ITEMS.seller_id.",
    "PRODUCT_CATEGORY_NAME_TRANSLATION": (
        "Lookup only. product_category_name (Portuguese slug) joins "
        "PRODUCTS.product_category_name; product_category_name_english is the display name."
    ),
    "PRODUCTS": (
        "product_category_name is a Portuguese slug -- join "
        "PRODUCT_CATEGORY_NAME_TRANSLATION for the English name. "
        "product_name_lenght / product_description_lenght are spelled that way "
        "in the real source column names (not a typo -- do not 'correct' them)."
    ),
    "GEOLOCATION": (
        "NOT deduplicated -- many rows per geolocation_zip_code_prefix (repeated "
        "geocode samples). Aggregate (e.g. AVG lat/lng per prefix) before joining "
        "or you will fan out row counts."
    ),
    "ORDERS": (
        "order_id is the primary key. customer_id joins CUSTOMERS.customer_id "
        "(one customer_id per order -- use CUSTOMERS.customer_unique_id for the "
        "person-level key)."
    ),
    "ORDER_ITEMS": (
        "One row per line item. Natural key (order_id, order_item_id). "
        "order_item_id is a per-order sequence number starting at 1, not globally unique. "
        "Joins ORDERS.order_id, PRODUCTS.product_id, SELLERS.seller_id."
    ),
    "ORDER_PAYMENTS": (
        "An order can have multiple payment rows (split/combined payment methods) -- "
        "natural key (order_id, payment_sequential). Sum payment_value per order_id "
        "when you need total order value, not a naive row count."
    ),
    "ORDER_REVIEWS": "review_id per order_id; an order can have more than one review row.",
}

TABLE_NAMES: tuple[str, ...] = tuple(OLIST_RAW_TABLES.keys())


_BUSINESS_GLOSSARY = """\
Business term glossary -- OLIST.RAW is a historical dump (no orders near the \
real calendar date), so "today"/"current"/"now" must NEVER be interpreted as \
CURRENT_DATE()/CURRENT_TIMESTAMP() -- always compute it from the data itself:
    "today" := (SELECT MAX(order_approved_at) FROM OLIST.RAW.ORDERS)
Every window below is relative to that "today", not the real calendar date.

Standard time windows:
- MAT ("Moving Annual Total", "trailing 12 months"): the 12-month window \
ending at "today" -- order_approved_at > DATEADD('year', -1, today) AND \
order_approved_at <= today.
- YTD ("year to date"): from Jan 1 of "today"'s year through "today" -- \
order_approved_at >= DATE_TRUNC('year', today) AND order_approved_at <= today.
- YA / "year ago" / "year-over-year" / "YoY": the same window (MAT or YTD) \
shifted back exactly one year using DATEADD('year', -1, ...) on both bounds -- \
never a naive 365-day subtraction (leap years).
- "Current"/"latest" alone, with no MAT/YTD stated: default to MAT unless the \
question clearly implies YTD or another explicit window.

Standard e-commerce measures (per line item in ORDER_ITEMS unless noted). Every \
measure below must exclude orders where ORDERS.order_status IN ('canceled', \
'unavailable') -- those never became real transactions and would overstate \
revenue/volume/freight if counted. Every other status (delivered, shipped, \
invoiced, processing, created, approved) counts, including orders still in \
flight -- "not yet delivered" is legitimate pipeline volume, not noise.
- Revenue / Dollar Sales / Sales: SUM(oi.price) -- excludes freight_value.
- Unit Sales / Units Sold: COUNT(oi.order_item_id).
- Volume Sales: SUM(p.product_weight_g) / 1000.0 (kilograms).
- Freight Cost / Shipping Cost: SUM(oi.freight_value).
- Freight Cost Ratio: SUM(oi.freight_value) / NULLIF(SUM(oi.price), 0).
- On-Time Delivery Rate: share of delivered orders (order_delivered_customer_date \
IS NOT NULL) where order_delivered_customer_date <= order_estimated_delivery_date.
- Delivery Lead Time: DATEDIFF('day', order_approved_at, order_delivered_customer_date), \
only for orders with a non-NULL order_delivered_customer_date.
- SKU / Product: PRODUCTS.product_id (Olist has no separate SKU table -- \
product_id is the finest-grained catalog identity available).
- Category: PRODUCT_CATEGORY_NAME_TRANSLATION.product_category_name_english -- \
always join through the translation table, since PRODUCTS.product_category_name \
is a Portuguese slug, not the display name.

Answering "top N X for the current period, with their YA figures" in one query: \
compute the current period's ranked top-N set first (a CTE), then LEFT JOIN that \
SAME set of keys against the year-ago window's totals. Do not run two independent \
top-N queries -- the year-ago top N by revenue is not necessarily the same set of \
products as the current top N, and the question is asking for the CURRENT top N's \
year-ago comparison, not a separate year-ago ranking. Example shape:

    WITH current_period AS (
        SELECT p.product_id, SUM(oi.price) AS revenue
        FROM OLIST.RAW.ORDER_ITEMS oi
        JOIN OLIST.RAW.ORDERS o ON oi.order_id = o.order_id
        JOIN OLIST.RAW.PRODUCTS p ON oi.product_id = p.product_id
        WHERE o.order_approved_at > DATEADD('year', -1, (SELECT MAX(order_approved_at) FROM OLIST.RAW.ORDERS))
          AND o.order_approved_at <= (SELECT MAX(order_approved_at) FROM OLIST.RAW.ORDERS)
          AND o.order_status NOT IN ('canceled', 'unavailable')
        GROUP BY p.product_id
        ORDER BY revenue DESC
        LIMIT 10
    ),
    year_ago AS (
        SELECT p.product_id, SUM(oi.price) AS revenue
        FROM OLIST.RAW.ORDER_ITEMS oi
        JOIN OLIST.RAW.ORDERS o ON oi.order_id = o.order_id
        JOIN OLIST.RAW.PRODUCTS p ON oi.product_id = p.product_id
        WHERE p.product_id IN (SELECT product_id FROM current_period)
          AND o.order_approved_at > DATEADD('year', -2, (SELECT MAX(order_approved_at) FROM OLIST.RAW.ORDERS))
          AND o.order_approved_at <= DATEADD('year', -1, (SELECT MAX(order_approved_at) FROM OLIST.RAW.ORDERS))
          AND o.order_status NOT IN ('canceled', 'unavailable')
        GROUP BY p.product_id
    )
    SELECT c.product_id, c.revenue AS revenue_mat, y.revenue AS revenue_mat_ya,
           c.revenue - COALESCE(y.revenue, 0) AS revenue_delta_abs
    FROM current_period c
    LEFT JOIN year_ago y ON c.product_id = y.product_id
    ORDER BY c.revenue DESC
"""


def format_business_glossary() -> str:
    """Render MAT/YTD/YA window definitions and standard e-commerce measure formulas.

    Grounds the NL-to-SQL model in the same business vocabulary already used
    by the deterministic KPI dashboards (`dashboards.ecommerce_kpis`,
    `dashboards.fulfillment`) -- MAT, YTD, year-ago deltas, revenue/unit/
    volume sales, on-time delivery rate, freight cost ratio -- so a chat
    question using those terms doesn't have to rely on the model's general
    knowledge (which has no way to know "today" means `MAX(order_approved_at)`
    in this specific historical dataset, not the real calendar date).

    Deliberately a separate function from `format_schema_context` -- that one
    is the byte-accurate table/column allowlist derived from the DDL; this is
    business semantics layered on top, a different concern that happens to
    also belong in the same prompt. Callers concatenate both into one
    `schema_context` (see `pages_.chat._build_initial_state`).
    """
    return _BUSINESS_GLOSSARY


def format_schema_context() -> str:
    """Render the OLIST.RAW allowlist into a compact text block for the LLM prompt.

    Produces one section per table: name, columns with types, and any FK/gotcha
    notes. Intended to be built once per app session (or once per graph run) and
    passed in via ``SnowstriderState["schema_context"]`` rather than re-derived
    on every node call.
    """
    lines = ["Schema: OLIST.RAW (Snowflake). Available tables:\n"]
    for table, columns in OLIST_RAW_TABLES.items():
        col_text = ", ".join(f"{name} {dtype}" for name, dtype in columns)
        lines.append(f"- OLIST.RAW.{table}: {col_text}")
        note = _TABLE_NOTES.get(table)
        if note:
            lines.append(f"    Note: {note}")
    return "\n".join(lines)
