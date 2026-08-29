"""Local hybrid retriever over a governed file corpus.

Implements keyword, vector-shaped and hybrid strategies without a service
dependency, so grounding, citations and entitlement trimming are all
demonstrable offline.

The "vector" component is a deterministic lexical embedding (character n-gram
hashing with cosine similarity). It is **not** a semantic embedding model and
makes no claim to be one: its job is to exercise the hybrid merge and reranking
path deterministically. Azure mode swaps in real embeddings via
``AzureSearchRetriever``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from contracts.common import Classification, utcnow
from contracts.retrieval import (
    RetrievalQuery,
    RetrievalResult,
    RetrievalStrategy,
    RetrievedItem,
)
from retrieval.base import RetrievalUnavailableError
from security.sanitisation import sanitise_untrusted

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-]{1,}")
_EMBEDDING_DIMS = 128


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _lexical_embedding(text: str) -> list[float]:
    """Deterministic hashed bag-of-trigrams. A stand-in, not a model."""
    vector = [0.0] * _EMBEDDING_DIMS
    normalised = " ".join(_tokens(text))
    for index in range(max(0, len(normalised) - 2)):
        trigram = normalised[index : index + 3]
        bucket = int.from_bytes(hashlib.blake2s(trigram.encode(), digest_size=2).digest(), "big")
        vector[bucket % _EMBEDDING_DIMS] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _resolve_updated_at(entry: dict[str, Any]) -> datetime:
    """Prefer a declared age over a fixed date.

    A corpus dated with absolute timestamps ages in real time, so a passage
    silently crosses its freshness SLO between one demo and the next and the
    disposition changes with it. `age_days` keeps a fixture's *relative* age
    constant, which is what "the same result on every machine" actually
    requires.
    """
    age_days = entry.get("age_days")
    if age_days is not None:
        return utcnow() - timedelta(days=int(age_days))
    return datetime.fromisoformat(entry["updated_at"])


class LocalKnowledgeRetriever:
    """Hybrid retrieval over JSON documents on disk."""

    def __init__(
        self,
        *,
        knowledge_dir: Path,
        index_name: str = "manufacturing-knowledge",
        index_version: str = "local-1",
    ) -> None:
        self.index_name = index_name
        self.index_version = index_version
        self._dir = knowledge_dir
        self._documents: list[RetrievedItem] = []
        self._embeddings: list[list[float]] = []
        self._loaded = False
        self.injection_signals: list[tuple[str, tuple[str, ...]]] = []

    def load(self) -> None:
        """Read and index the corpus. Idempotent."""
        if self._loaded:
            return
        if not self._dir.is_dir():
            raise RetrievalUnavailableError(f"knowledge directory not found: {self._dir}")

        documents: list[RetrievedItem] = []
        for path in sorted(self._dir.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            for entry in raw.get("passages", []):
                sanitised = sanitise_untrusted(entry["passage"])
                if sanitised.suspicious:
                    # Recorded, not silently dropped: an injection attempt in
                    # the corpus is a governance finding about the corpus.
                    self.injection_signals.append((entry["source_id"], sanitised.signals))
                documents.append(
                    RetrievedItem(
                        source_id=entry["source_id"],
                        source_title=entry["source_title"],
                        passage=sanitised.text,
                        source_uri=entry["source_uri"],
                        version=entry["version"],
                        updated_at=_resolve_updated_at(entry),
                        classification=Classification(entry.get("classification", "internal")),
                        access_groups=frozenset(entry["access_groups"]),
                        authority=entry.get("authority", "secondary"),
                        score=0.0,
                        citation_ref=entry["source_id"],
                        freshness_slo_days=entry.get("freshness_slo_days", 90),
                    )
                )

        if not documents:
            raise RetrievalUnavailableError(f"no knowledge documents found in {self._dir}")

        self._documents = documents
        self._embeddings = [_lexical_embedding(d.passage + " " + d.source_title) for d in documents]
        self._loaded = True

    async def healthy(self) -> bool:
        try:
            self.load()
        except RetrievalUnavailableError:
            return False
        return True

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        started = time.perf_counter()
        self.load()

        # Entitlement and classification are applied before scoring, so a
        # document the caller may not see is never ranked, never truncated into
        # a context window and never leaks its existence through a score.
        permitted, trimmed = self._trim(self._documents, query)

        scored = self._score(permitted, query)
        ranked = sorted(scored, key=lambda pair: -pair[1])[: query.top_k]
        items = tuple(item.model_copy(update={"score": round(score, 4)}) for item, score in ranked)

        return RetrievalResult(
            query_id=query.query_id,
            correlation_id=query.correlation_id,
            strategy=query.strategy,
            items=items,
            subqueries=(query.text,),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            index_name=self.index_name,
            index_version=self.index_version,
            trimmed_count=trimmed,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _trim(
        documents: Iterable[RetrievedItem], query: RetrievalQuery
    ) -> tuple[list[RetrievedItem], int]:
        permitted: list[RetrievedItem] = []
        trimmed = 0
        for document in documents:
            entitled = bool(document.access_groups & query.entitlement_groups)
            within_classification = document.classification.rank <= query.max_classification.rank
            if entitled and within_classification:
                permitted.append(document)
            else:
                trimmed += 1
        return permitted, trimmed

    def _score(
        self, documents: list[RetrievedItem], query: RetrievalQuery
    ) -> list[tuple[RetrievedItem, float]]:
        query_tokens = Counter(_tokens(query.text))
        query_vector = _lexical_embedding(query.text)
        indexed = {id(doc): i for i, doc in enumerate(self._documents)}

        results: list[tuple[RetrievedItem, float]] = []
        for document in documents:
            keyword = self._keyword_score(document, query_tokens)
            vector = _cosine(query_vector, self._embeddings[indexed[id(document)]])

            match query.strategy:
                case RetrievalStrategy.KEYWORD:
                    score = keyword
                case RetrievalStrategy.VECTOR:
                    score = vector
                case RetrievalStrategy.SEMANTIC:
                    score = vector * 0.7 + keyword * 0.3
                case _:
                    # Hybrid and agentic both merge the two signals; agentic
                    # differs in how many queries reach this function, not in
                    # how a single document is scored.
                    score = keyword * 0.5 + vector * 0.5

            # Authoritative sources outrank secondary ones at equal relevance,
            # which is how "which source wins" becomes a property of the index
            # rather than an argument at answer time.
            if document.authority == "authoritative":
                score *= 1.25
            elif document.authority == "reference":
                score *= 0.9
            if document.is_stale():
                score *= 0.75

            if score > 0:
                results.append((document, score))
        return results

    @staticmethod
    def _keyword_score(document: RetrievedItem, query_tokens: Counter[str]) -> float:
        if not query_tokens:
            return 0.0
        haystack = Counter(_tokens(document.passage + " " + document.source_title))
        overlap = sum(min(count, haystack[token]) for token, count in query_tokens.items())
        return overlap / sum(query_tokens.values())
