"""Wires the Snowstrider node functions into a compiled langgraph StateGraph.

    translate_question -> generate_sql -> validate_sql
      valid                    -> execute_sql
      invalid, attempts remain -> generate_sql
      invalid, exhausted       -> give_up -> END

    execute_sql
      success                  -> self_check
      error, attempts remain   -> generate_sql
      error, exhausted         -> give_up -> END

    self_check
      plausible                    -> chart_spec -> END
      implausible, attempts remain -> generate_sql
      implausible, exhausted       -> mark_low_confidence -> chart_spec -> END

`attempt_count` is shared across all three retry edges (validation failure,
execution failure, implausibility) -- it is incremented once per
`generate_sql` call, not per edge, so `max_attempts=3` caps the total number
of `generate_sql` calls for a single question regardless of which stage kept
failing.
"""

from __future__ import annotations

import logging

import anthropic
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from snowflake.snowpark import Session

from graph.nodes.chart_spec import make_chart_spec_node
from graph.nodes.execute_sql import make_execute_sql_node
from graph.nodes.generate_sql import make_generate_sql_node
from graph.nodes.self_check import make_self_check_node
from graph.nodes.translate_question import make_translate_question_node
from graph.nodes.validate_sql import validate_sql
from graph.state import SnowstriderState

logger = logging.getLogger(__name__)

NODE_TRANSLATE_QUESTION = "translate_question"
NODE_GENERATE_SQL = "generate_sql"
NODE_VALIDATE_SQL = "validate_sql"
NODE_EXECUTE_SQL = "execute_sql"
NODE_SELF_CHECK = "self_check"
# NOTE: cannot be named "chart_spec" -- langgraph rejects a node name that
# collides with a key in the state schema, and "chart_spec" is a
# SnowstriderState key (the field the node writes its output into).
NODE_CHART_SPEC = "build_chart_spec"
NODE_GIVE_UP = "give_up"
NODE_MARK_LOW_CONFIDENCE = "mark_low_confidence"


def route_after_validate(state: SnowstriderState) -> str:
    """Route after `validate_sql`: on to execution, back to generation, or give up."""
    if state.get("validation_error") is None:
        return NODE_EXECUTE_SQL
    if state["attempt_count"] < state["max_attempts"]:
        return NODE_GENERATE_SQL
    return NODE_GIVE_UP


def route_after_execute(state: SnowstriderState) -> str:
    """Route after `execute_sql`: on to the plausibility check, back to generation, or give up."""
    if state.get("execution_error") is None:
        return NODE_SELF_CHECK
    if state["attempt_count"] < state["max_attempts"]:
        return NODE_GENERATE_SQL
    return NODE_GIVE_UP


def route_after_self_check(state: SnowstriderState) -> str:
    """Route after `self_check`: on to charting, back to generation, or charting-with-caveat."""
    if state.get("self_check_passed"):
        return NODE_CHART_SPEC
    if state["attempt_count"] < state["max_attempts"]:
        return NODE_GENERATE_SQL
    return NODE_MARK_LOW_CONFIDENCE


def _give_up_node(state: SnowstriderState) -> dict:
    """Set `final_error` from whichever failure caused the retry budget to be exhausted."""
    error = state.get("validation_error") or state.get("execution_error") or "unknown failure"
    logger.error("give_up: exhausted %d attempts, final error: %s", state["attempt_count"], error)
    return {"final_error": error}


def _mark_low_confidence_node(state: SnowstriderState) -> dict:
    """Flag the run as low-confidence after exhausting retries on an implausible result.

    We still proceed to `chart_spec` (rather than giving up) because the
    query *executed successfully* -- it just didn't pass the plausibility
    check -- so there is a real result worth showing, with a caveat.
    """
    logger.warning(
        "mark_low_confidence: exhausted %d attempts, self-check never passed: %s",
        state["attempt_count"], state.get("self_check_reasoning"),
    )
    return {"low_confidence": True}


def build_graph(session: Session, anthropic_client: anthropic.Anthropic) -> CompiledStateGraph:
    """Build and compile the Snowstrider StateGraph.

    Binds `session` (Snowpark) and `anthropic_client` (Anthropic) into the
    node closures that need them via each node module's `make_*_node`
    factory -- langgraph node functions only ever receive `state`, so the
    external clients have to be captured at build time rather than passed
    per-call.
    """
    graph = StateGraph(SnowstriderState)

    graph.add_node(NODE_TRANSLATE_QUESTION, make_translate_question_node(anthropic_client))
    graph.add_node(NODE_GENERATE_SQL, make_generate_sql_node(anthropic_client))
    graph.add_node(NODE_VALIDATE_SQL, validate_sql)
    graph.add_node(NODE_EXECUTE_SQL, make_execute_sql_node(session))
    graph.add_node(NODE_SELF_CHECK, make_self_check_node(anthropic_client))
    graph.add_node(NODE_CHART_SPEC, make_chart_spec_node(anthropic_client))
    graph.add_node(NODE_GIVE_UP, _give_up_node)
    graph.add_node(NODE_MARK_LOW_CONFIDENCE, _mark_low_confidence_node)

    graph.set_entry_point(NODE_TRANSLATE_QUESTION)
    graph.add_edge(NODE_TRANSLATE_QUESTION, NODE_GENERATE_SQL)
    graph.add_edge(NODE_GENERATE_SQL, NODE_VALIDATE_SQL)

    graph.add_conditional_edges(NODE_VALIDATE_SQL, route_after_validate)
    graph.add_conditional_edges(NODE_EXECUTE_SQL, route_after_execute)
    graph.add_conditional_edges(NODE_SELF_CHECK, route_after_self_check)

    graph.add_edge(NODE_MARK_LOW_CONFIDENCE, NODE_CHART_SPEC)
    graph.add_edge(NODE_CHART_SPEC, END)
    graph.add_edge(NODE_GIVE_UP, END)

    return graph.compile()
