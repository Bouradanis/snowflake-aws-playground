"""Tests for pages_.chat -- `_build_initial_state`'s pure state-construction logic.

No Streamlit/Snowflake/Anthropic involved: `_build_initial_state` just builds
a plain dict, no widgets rendered, no network calls made.
"""

from __future__ import annotations

from pages_.chat import _build_initial_state


def test_build_initial_state_includes_business_glossary_in_schema_context() -> None:
    state = _build_initial_state("top 10 SKUs by revenue")

    assert "MAT" in state["schema_context"]
    assert "Moving Annual Total" in state["schema_context"]
    assert "OLIST.RAW.ORDERS" in state["schema_context"]  # still has the table allowlist too


def test_build_initial_state_analytical_brief_starts_none() -> None:
    # Populated by the translate_question node once the graph runs -- not
    # known yet at initial-state construction time.
    state = _build_initial_state("top 10 SKUs by revenue")
    assert state["analytical_brief"] is None


def test_build_initial_state_preserves_the_raw_question() -> None:
    state = _build_initial_state("how many orders shipped last week?")
    assert state["question"] == "how many orders shipped last week?"