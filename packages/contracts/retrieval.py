"""Retrieval contracts.

Retrieved content is untrusted input. It carries authority, entitlement,
freshness and a citation reference so that a downstream component can refuse to
use it, rather than discovering the problem in an answer.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.common import Classification, PlatformModel, new_id, utcnow


class RetrievalStrategy(StrEnum):
    KEYWORD = "keyword"
    VECTOR = "vector"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    AGENTIC = "agentic"


class RetrievalQuery(PlatformModel):
    """A query plus the caller's entitlements. Entitlements are never optional."""

    query_id: str = Field(default_factory=lambda: new_id("q"))
    correlation_id: str
    text: str = Field(min_length=1, max_length=4_000)
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    top_k: int = Field(default=5, ge=1, le=50)
    # Empty entitlements means "entitled to nothing", never "entitled to all".
    entitlement_groups: frozenset[str]
    max_classification: Classification = Classification.CONFIDENTIAL
    filters: tuple[tuple[str, str], ...] = ()
    max_subqueries: int = Field(default=4, ge=1, le=8)


class RetrievedItem(PlatformModel):
    """One passage, with everything needed to cite it and to refuse it."""

    source_id: str = Field(min_length=1, max_length=128)
    source_title: str = Field(min_length=1, max_length=300)
    passage: str = Field(min_length=1)
    source_uri: str
    version: str = Field(min_length=1, max_length=64)
    updated_at: datetime
    classification: Classification
    access_groups: frozenset[str]
    authority: str = Field(default="secondary", pattern=r"^(authoritative|secondary|reference)$")
    score: float = Field(ge=0.0)
    citation_ref: str = Field(min_length=1, max_length=32)
    freshness_slo_days: int = Field(default=90, gt=0)

    def is_stale(self, *, now: datetime | None = None) -> bool:
        reference = now or utcnow()
        return (reference - self.updated_at) > timedelta(days=self.freshness_slo_days)


class RetrievalResult(PlatformModel):
    """Retrieval output, including an honest account of what did not work.

    ``partial`` plus ``failures`` exists so a caller can choose to answer with a
    caveat, retry, or refuse. Silently returning half the evidence is the
    failure mode this field prevents.
    """

    query_id: str
    correlation_id: str
    strategy: RetrievalStrategy
    items: tuple[RetrievedItem, ...]
    subqueries: tuple[str, ...] = ()
    latency_ms: float = Field(ge=0.0)
    index_name: str
    index_version: str
    trimmed_count: int = Field(default=0, ge=0)
    partial: bool = False
    failures: tuple[str, ...] = ()
    retrieved_at: datetime = Field(default_factory=utcnow)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0

    @property
    def has_authoritative_source(self) -> bool:
        return any(item.authority == "authoritative" for item in self.items)

    def stale_items(self, *, now: datetime | None = None) -> tuple[RetrievedItem, ...]:
        return tuple(item for item in self.items if item.is_stale(now=now))

    @model_validator(mode="after")
    def _partial_requires_reason(self) -> Self:
        if self.partial and not self.failures:
            raise ValueError("partial results must explain what failed")
        refs = [item.citation_ref for item in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("citation_ref must be unique within a result set")
        return self
