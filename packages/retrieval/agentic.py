"""Agentic retrieval: decompose, retrieve in parallel, merge and rerank.

Improves recall on multi-part questions and costs latency, tokens, an extra
planning failure mode and a larger authorization surface. Budgets are therefore
first class: a bounded subquery count, a planning timeout, a per-subquery
timeout, and a documented degradation to single-shot retrieval.

Every subquery inherits the **caller's** entitlements, never the planner's,
which closes the most obvious authorization gap in this pattern.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from contracts.retrieval import RetrievalQuery, RetrievalResult, RetrievalStrategy, RetrievedItem
from retrieval.base import RetrievalUnavailableError, Retriever

Planner = Callable[[str, int], Awaitable[list[str]]]

PLAN_TIMEOUT_S = 4.0
SUBQUERY_TIMEOUT_S = 6.0


async def deterministic_planner(question: str, max_subqueries: int) -> list[str]:
    """Rule-based decomposition used in local mode.

    Splits on conjunctions and question boundaries. Not a model, and does not
    pretend to be one — its purpose is to exercise the fan-out, merge and budget
    behaviour deterministically.
    """
    fragments = [
        fragment.strip()
        for fragment in question.replace("?", "?|").replace(" and ", "|").split("|")
        if len(fragment.strip()) >= 8
    ]
    return (fragments or [question])[:max_subqueries]


class AgenticRetriever:
    """Wraps any retriever with a planner and a budget."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        planner: Planner = deterministic_planner,
        max_subqueries: int = 4,
    ) -> None:
        self._retriever = retriever
        self._planner = planner
        self._max_subqueries = max_subqueries
        self.index_name = retriever.index_name
        self.index_version = retriever.index_version

    async def healthy(self) -> bool:
        return await self._retriever.healthy()

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        started = time.perf_counter()
        subqueries = await self._plan(query)

        tasks = [asyncio.create_task(self._run_subquery(query, text)) for text in subqueries]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        merged: dict[str, RetrievedItem] = {}
        failures: list[str] = []
        trimmed = 0

        for text, outcome in zip(subqueries, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                failures.append(text)
                continue
            trimmed += outcome.trimmed_count
            for item in outcome.items:
                existing = merged.get(item.citation_ref)
                if existing is None or item.score > existing.score:
                    merged[item.citation_ref] = item

        if not merged and failures:
            raise RetrievalUnavailableError(
                "every subquery failed", correlation_id=query.correlation_id
            )

        ranked = sorted(merged.values(), key=lambda item: -item.score)[: query.top_k]
        return RetrievalResult(
            query_id=query.query_id,
            correlation_id=query.correlation_id,
            strategy=RetrievalStrategy.AGENTIC,
            items=tuple(ranked),
            subqueries=tuple(subqueries),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            index_name=self.index_name,
            index_version=self.index_version,
            trimmed_count=trimmed,
            # An honest partial result: the caller decides whether to answer
            # with a caveat, retry, or refuse. Silently returning half the
            # evidence is the failure this field prevents.
            partial=bool(failures),
            failures=tuple(failures),
        )

    async def _plan(self, query: RetrievalQuery) -> list[str]:
        budget = min(query.max_subqueries, self._max_subqueries)
        try:
            async with asyncio.timeout(PLAN_TIMEOUT_S):
                planned = await self._planner(query.text, budget)
        except (TimeoutError, Exception):
            # Degrade to single-shot. Lower recall is acceptable; a stalled
            # retrieval path is not.
            return [query.text]
        # Cap the fan-out in code. A prompt asking for at most N is a request;
        # slicing the validated list is a control.
        return (planned or [query.text])[:budget]

    async def _run_subquery(self, query: RetrievalQuery, text: str) -> RetrievalResult:
        async with asyncio.timeout(SUBQUERY_TIMEOUT_S):
            return await self._retriever.search(
                query.model_copy(update={"text": text, "strategy": RetrievalStrategy.HYBRID})
            )
