"""LangGraph state shape shared by every node in the Snowstrider graph."""

from __future__ import annotations

from typing import Optional, TypedDict


class SnowstriderState(TypedDict):
    """State threaded through the Snowstrider LangGraph state graph.

    Every node function is `(state: SnowstriderState) -> dict` and returns a
    *partial* update (the langgraph convention) -- only the keys it changes.
    """

    question: str
    schema_context: str
    analytical_brief: Optional[str]
    sql_candidate: Optional[str]
    validation_error: Optional[str]
    execution_error: Optional[str]
    result_columns: Optional[list[str]]
    result_preview: Optional[list[dict]]  # small row sample only, e.g. first 10 rows as dicts
    result_row_count: Optional[int]
    self_check_passed: Optional[bool]
    self_check_reasoning: Optional[str]
    chart_spec: Optional[dict]
    attempt_count: int
    max_attempts: int  # default 3
    final_error: Optional[str]
    low_confidence: bool
