"""Pure, defensive Plotly chart renderer for LLM-produced chart specs.

`render_chart` never raises -- any invalid/inconsistent spec (missing
columns, unknown chart type, empty data) results in `None`, and the caller
(`app.py`) is expected to fall back to showing the results table only.

Security note: `chart_spec` values originate from an LLM tool-use response
(see `graph/nodes/chart_spec.py`) and are therefore untrusted input. Every
value out of it is used *only* as a column-name lookup against the real
DataFrame or as a key into the fixed enum-to-Plotly-Express mapping below --
never passed to `eval()`/`exec()` or used to build code.
"""

from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

_VALID_CHART_TYPES = {"bar", "line", "scatter", "pie"}
_VALID_AGGS = {"sum", "avg", "count", "none"}
_PANDAS_AGG = {"sum": "sum", "avg": "mean", "count": "count"}

# Matches Streamlit's dark theme, which this app runs under -- avoids Plotly's
# default light-on-white template clashing with the surrounding page chrome.
_TEMPLATE = "plotly_dark"

# Purple as the primary brand color (matches .streamlit/config.toml's
# primaryColor), amber/orange as complements -- picked over Plotly's default
# blue palette because a flat single-hue BI tool reads as unfinished.
_PURPLE = "#8B5CF6"
_COLOR_SEQUENCE = ["#8B5CF6", "#F59E0B", "#FB923C", "#C084FC", "#FCD34D"]


def render_chart(df: pd.DataFrame, chart_spec: dict) -> go.Figure | None:
    """Build a Plotly figure from a query result DataFrame and a chart spec.

    `chart_spec` is expected to look like:
        {"chart_type": "bar"|"line"|"scatter"|"pie"|"none",
         "x": str, "y": str, "color": str, "agg": "sum"|"avg"|"count"|"none",
         "title": str}

    Returns `None` (never raises) when:
      - `chart_spec` isn't a dict, or `chart_type` is `"none"`/unrecognized
      - `df` is `None` or empty
      - `x`/`y` are missing from the spec or don't exist as columns in `df`
      - `color` is given but doesn't exist as a column in `df`
      - chart construction fails for any other reason
    """
    if not isinstance(chart_spec, dict):
        return None

    chart_type = chart_spec.get("chart_type")
    if chart_type not in _VALID_CHART_TYPES:
        return None

    if df is None or df.empty:
        logger.info("render_chart: empty or missing dataframe, skipping chart")
        return None

    x_col = chart_spec.get("x")
    y_col = chart_spec.get("y")
    color_col = chart_spec.get("color") or None
    agg = chart_spec.get("agg", "none")
    if agg not in _VALID_AGGS:
        agg = "none"
    title = chart_spec.get("title") or None

    if not x_col or not y_col:
        return None
    if x_col not in df.columns or y_col not in df.columns:
        return None
    if color_col and color_col not in df.columns:
        return None

    # Plotly Express has no Vega-Lite-style implicit aggregation transform --
    # pre-aggregate with pandas when the spec asks for it, so multiple rows
    # per category collapse into one bar/point instead of plotting raw rows.
    plot_df = df
    if agg != "none":
        group_cols = [x_col] + ([color_col] if color_col else [])
        plot_df = df.groupby(group_cols, as_index=False)[y_col].agg(_PANDAS_AGG[agg])

    try:
        if chart_type == "bar":
            # Rank bars by value (highest first) instead of Plotly's default
            # first-seen/alphabetical category order -- matches how a human
            # reads a "top N" question.
            plot_df = plot_df.sort_values(y_col, ascending=False)
            fig = px.bar(
                plot_df, x=x_col, y=y_col, color=color_col, title=title,
                template=_TEMPLATE, text_auto=".2s",
                color_discrete_sequence=_COLOR_SEQUENCE,
            )
            fig.update_traces(textposition="outside")
            if not color_col:
                fig.update_traces(marker_color=_PURPLE)
        elif chart_type == "line":
            fig = px.line(
                plot_df, x=x_col, y=y_col, color=color_col, title=title,
                template=_TEMPLATE, markers=True,
                color_discrete_sequence=_COLOR_SEQUENCE,
            )
            if not color_col:
                fig.update_traces(line_color=_PURPLE, marker_color=_PURPLE)
        elif chart_type == "scatter":
            fig = px.scatter(
                plot_df, x=x_col, y=y_col, color=color_col, title=title,
                template=_TEMPLATE,
                color_discrete_sequence=_COLOR_SEQUENCE,
            )
            if not color_col:
                fig.update_traces(marker_color=_PURPLE)
        elif chart_type == "pie":
            # Pie charts use names/values (the category/slice-size pair)
            # rather than x/y -- x becomes the category slice, y (aggregated
            # if requested) becomes the slice size. Always effectively
            # "colored" (one color per slice), so always uses the full sequence.
            fig = px.pie(
                plot_df, names=x_col, values=y_col, title=title, template=_TEMPLATE,
                color_discrete_sequence=_COLOR_SEQUENCE,
            )
        else:  # pragma: no cover - unreachable, chart_type already validated above
            return None

        fig.update_xaxes(tickangle=-40)
        fig.update_layout(margin=dict(t=60, b=80))
        return fig
    except Exception:
        logger.exception("render_chart: failed to build chart for spec %s", chart_spec)
        return None