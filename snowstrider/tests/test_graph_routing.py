"""Tests for the conditional-edge routing functions in graph.build_graph.

These are plain functions of `SnowstriderState -> str`, imported and called
directly with hand-built state dicts -- no compiled graph, no Snowflake/
Anthropic clients needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from graph.build_graph import (
    NODE_CHART_SPEC,
    NODE_EXECUTE_SQL,
    NODE_GENERATE_SQL,
    NODE_GIVE_UP,
    NODE_MARK_LOW_CONFIDENCE,
    NODE_TRANSLATE_QUESTION,
    build_graph,
    route_after_execute,
    route_after_self_check,
    route_after_validate,
)
from graph.state import SnowstriderState


def _base_state(**overrides) -> SnowstriderState:
    state: SnowstriderState = {
        "question": "How many orders were delivered?",
        "schema_context": "irrelevant for routing tests",
        "analytical_brief": None,
        "sql_candidate": "SELECT 1",
        "validation_error": None,
        "execution_error": None,
        "result_columns": None,
        "result_preview": None,
        "result_row_count": None,
        "self_check_passed": None,
        "self_check_reasoning": None,
        "chart_spec": None,
        "attempt_count": 1,
        "max_attempts": 3,
        "final_error": None,
        "low_confidence": False,
    }
    state.update(overrides)
    return state


# ── route_after_validate ─────────────────────────────────────────────────────

def test_route_after_validate_success_goes_to_execute() -> None:
    state = _base_state(validation_error=None)
    assert route_after_validate(state) == NODE_EXECUTE_SQL


def test_route_after_validate_failure_with_attempts_remaining_retries() -> None:
    state = _base_state(validation_error="bad SQL", attempt_count=1, max_attempts=3)
    assert route_after_validate(state) == NODE_GENERATE_SQL


def test_route_after_validate_failure_exhausted_gives_up() -> None:
    state = _base_state(validation_error="bad SQL", attempt_count=3, max_attempts=3)
    assert route_after_validate(state) == NODE_GIVE_UP


# ── route_after_execute ──────────────────────────────────────────────────────

def test_route_after_execute_success_goes_to_self_check() -> None:
    state = _base_state(execution_error=None)
    assert route_after_execute(state) == "self_check"


def test_route_after_execute_failure_with_attempts_remaining_retries() -> None:
    state = _base_state(execution_error="timeout", attempt_count=2, max_attempts=3)
    assert route_after_execute(state) == NODE_GENERATE_SQL


def test_route_after_execute_failure_exhausted_gives_up() -> None:
    state = _base_state(execution_error="timeout", attempt_count=3, max_attempts=3)
    assert route_after_execute(state) == NODE_GIVE_UP


# ── route_after_self_check ───────────────────────────────────────────────────

def test_route_after_self_check_plausible_goes_to_chart_spec() -> None:
    state = _base_state(self_check_passed=True)
    assert route_after_self_check(state) == NODE_CHART_SPEC


def test_route_after_self_check_implausible_with_attempts_remaining_retries() -> None:
    state = _base_state(self_check_passed=False, attempt_count=1, max_attempts=3)
    assert route_after_self_check(state) == NODE_GENERATE_SQL


def test_route_after_self_check_implausible_exhausted_marks_low_confidence() -> None:
    state = _base_state(self_check_passed=False, attempt_count=3, max_attempts=3)
    assert route_after_self_check(state) == NODE_MARK_LOW_CONFIDENCE


def test_max_attempts_is_a_total_budget_shared_across_all_three_branch_points() -> None:
    # attempt_count is incremented once per generate_sql call, regardless of
    # which stage (validate/execute/self_check) triggered the retry -- so at
    # attempt_count == max_attempts, every branch point gives up/stops
    # retrying, not just the one that happened to fail last.
    exhausted = _base_state(attempt_count=3, max_attempts=3)

    assert route_after_validate({**exhausted, "validation_error": "x"}) == NODE_GIVE_UP
    assert route_after_execute({**exhausted, "execution_error": "x"}) == NODE_GIVE_UP
    assert route_after_self_check({**exhausted, "self_check_passed": False}) == NODE_MARK_LOW_CONFIDENCE


# ── build_graph wiring ────────────────────────────────────────────────────────


def test_translate_question_is_the_graph_entry_point() -> None:
    # translate_question (the e-commerce BI specialist) must run before any
    # SQL is generated -- session/client are never called at build time, so
    # MagicMocks are safe here.
    compiled = build_graph(session=MagicMock(), anthropic_client=MagicMock())
    edges = {(e.source, e.target) for e in compiled.get_graph().edges}

    assert ("__start__", NODE_TRANSLATE_QUESTION) in edges
    assert (NODE_TRANSLATE_QUESTION, NODE_GENERATE_SQL) in edges
