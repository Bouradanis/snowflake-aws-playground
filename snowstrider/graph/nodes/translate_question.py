"""translate_question node -- an e-commerce BI specialist that runs before any SQL is written.

Motivation: `generate_sql`'s system prompt is a SQL-writing specification, not
a business-analysis one -- it's good at "translate this precise spec into
correct Snowflake SQL" but has no dedicated step for resolving ambiguous
business terms (MAT, YTD, YA, "revenue") or noticing that a compound question
("top 10 X for the current period, AND show their YA difference") has two
parts that both need to make it into the query. Without this node, a
multi-part question silently had its harder half dropped: the model would
generate SQL for the well-defined half and self_check would still rate a
clean, well-shaped partial result as "plausible" (it only judges shape, not
completeness against every clause of the original ask).

This node runs once, before `generate_sql`, and is NOT part of the
validate/execute/self_check retry loop -- retries are about SQL correctness
against a fixed brief, not about re-interpreting intent on every attempt.
"""

from __future__ import annotations

import logging
from typing import Callable

import anthropic

from graph.state import SnowstriderState

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

_SYSTEM_PROMPT_TEMPLATE = """You are a senior e-commerce BI analyst working alongside a SQL engineer. \
The engineer only writes SQL -- they don't resolve business terminology or catch missing pieces of a \
request on their own. Your job is to read the user's question and rewrite it as a precise, complete, \
unambiguous analytical brief the SQL engineer can implement directly, using the business glossary and \
schema below.

{schema_context}

Rules for the brief:
- Resolve every business term (MAT, YTD, YA, revenue, SKU, on-time rate, freight cost ratio, etc.) into \
its exact definition/formula from the glossary above -- do not leave any term for the SQL engineer to \
interpret on their own.
- If the question has multiple parts (e.g. "top N X, and also show their Y"), spell out EVERY part \
explicitly and how they relate to each other (e.g. "the Y figures must be for the SAME N items \
identified in the first part, not a separately-computed set").
- State the exact grain (e.g. "one row per product_id") and the exact measure/aggregation to use for \
each part of the question.
- Do not write SQL yourself -- describe what the query must compute, in plain English, precisely \
enough that a competent SQL engineer with no other context could not misinterpret it.
- If the question is already unambiguous and simple, a short brief is fine -- don't pad it.
- Output ONLY the brief. No preamble, no "Here is the brief:", no markdown headers.
"""


def make_translate_question_node(client: anthropic.Anthropic) -> Callable[[SnowstriderState], dict]:
    """Build the `translate_question` node, closing over the Anthropic client."""

    def translate_question(state: SnowstriderState) -> dict:
        """Call Claude to turn the raw question into a SQL-ready analytical brief."""
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(schema_context=state["schema_context"])

        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": state["question"]}],
            )
            brief = message.content[0].text.strip()
        except anthropic.APIError as exc:
            logger.error("translate_question: Anthropic API call failed: %s", exc)
            # A translation-quality enhancement failing shouldn't fail the
            # whole graph run -- degrade to generate_sql working off the raw
            # question, the pre-existing behavior, rather than a new failure mode.
            return {"analytical_brief": state["question"]}

        logger.info("translate_question: produced analytical brief")
        return {"analytical_brief": brief}

    return translate_question