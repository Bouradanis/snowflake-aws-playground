"""Deterministic BI/reporting dashboards for Snowstrider.

Unlike `snowstrider.graph` (the NL-to-SQL LangGraph pipeline), everything
under this package is hand-written SQL + Python date math -- no LLM calls,
no `langgraph`, no `sql_guard` validation (there's no LLM-generated SQL here
to validate). Modules in this package are the data/logic layer consumed by
the Streamlit UI; they contain no `streamlit` imports themselves.
"""

from __future__ import annotations
