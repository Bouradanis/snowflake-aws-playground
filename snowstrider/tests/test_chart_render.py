"""Tests for charts.render.render_chart -- pure, defensive chart builder.

No Streamlit, no network calls -- just DataFrame + dict in, `go.Figure | None` out.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from charts.render import render_chart


@pytest.fixture
def fixture_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "product_category_name_english": ["health_beauty", "sports_leisure", "furniture"],
            "revenue": [1200.50, 980.25, 430.10],
            "order_status": ["delivered", "delivered", "shipped"],
        }
    )


def test_valid_spec_returns_a_chart(fixture_df: pd.DataFrame) -> None:
    spec = {
        "chart_type": "bar",
        "x": "product_category_name_english",
        "y": "revenue",
        "color": "",
        "agg": "none",
        "title": "Revenue by category",
    }
    chart = render_chart(fixture_df, spec)
    assert isinstance(chart, go.Figure)


def test_bar_chart_sorts_by_value_descending(fixture_df: pd.DataFrame) -> None:
    spec = {
        "chart_type": "bar",
        "x": "product_category_name_english",
        "y": "revenue",
        "color": "",
        "agg": "none",
        "title": "",
    }
    chart = render_chart(fixture_df, spec)
    x_values = list(chart.data[0].x)
    assert x_values == ["health_beauty", "sports_leisure", "furniture"]


def test_spec_referencing_nonexistent_column_returns_none(fixture_df: pd.DataFrame) -> None:
    spec = {
        "chart_type": "bar",
        "x": "product_category_name_english",
        "y": "does_not_exist",
        "color": "",
        "agg": "none",
        "title": "",
    }
    assert render_chart(fixture_df, spec) is None


def test_chart_type_none_returns_none(fixture_df: pd.DataFrame) -> None:
    spec = {
        "chart_type": "none",
        "x": "product_category_name_english",
        "y": "revenue",
        "color": "",
        "agg": "none",
        "title": "",
    }
    assert render_chart(fixture_df, spec) is None


def test_nonexistent_color_column_returns_none(fixture_df: pd.DataFrame) -> None:
    spec = {
        "chart_type": "bar",
        "x": "product_category_name_english",
        "y": "revenue",
        "color": "does_not_exist",
        "agg": "none",
        "title": "",
    }
    assert render_chart(fixture_df, spec) is None


def test_empty_dataframe_returns_none() -> None:
    spec = {"chart_type": "bar", "x": "a", "y": "b", "color": "", "agg": "none", "title": ""}
    assert render_chart(pd.DataFrame(), spec) is None


def test_not_a_dict_returns_none(fixture_df: pd.DataFrame) -> None:
    assert render_chart(fixture_df, None) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("chart_type", ["bar", "line", "scatter", "pie"])
def test_each_chart_type_renders_without_raising(fixture_df: pd.DataFrame, chart_type: str) -> None:
    spec = {
        "chart_type": chart_type,
        "x": "product_category_name_english",
        "y": "revenue",
        "color": "order_status",
        "agg": "sum",
        "title": f"{chart_type} chart",
    }
    chart = render_chart(fixture_df, spec)
    assert isinstance(chart, go.Figure)


def test_missing_x_or_y_key_returns_none(fixture_df: pd.DataFrame) -> None:
    spec = {"chart_type": "bar", "x": "", "y": "revenue", "color": "", "agg": "none", "title": ""}
    assert render_chart(fixture_df, spec) is None