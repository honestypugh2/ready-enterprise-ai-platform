"""Azure AI Search retriever.

The single most important line in this module is the entitlement filter. It is
applied server side, as part of the query, so a document the caller may not see
is never retrieved, never ranked and never reaches a model's context window.

Filtering after retrieval is a common shortcut and it leaks both the content and
the existence of the content.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from contracts.common import Classification
from contracts.retrieval import RetrievalQuery, RetrievalResult, RetrievalStrategy, RetrievedItem
from retrieval.base import RetrievalUnavailableError
from security.sanitisation import sanitise_untrusted

SELECT_FIELDS = (
    "source_id",
    "source_title",
    "passage",
    "source_uri",
    "version",
    "updated_at",
    "classification",
    "access_groups",
    "authority",
)


class AzureSearchRetriever:
    """Hybrid search against an Azure AI Search index with query-time trimming."""

    def __init__(
        self,
        *,
        endpoint: str,
        index_name: str,
        credential: Any,
        index_version: str = "unknown",
        semantic_configuration: str = "default",
        embed: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.index_name = index_name
        self.index_version = index_version
        self._endpoint = endpoint
        self._credential = credential
        self._semantic_configuration = semantic_configuration
        self._embed = embed
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from azure.search.documents.aio import SearchClient  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RetrievalUnavailableError(
                "azure-search-documents is not installed; run `uv sync --extra azure`"
            ) from exc
        self._client = SearchClient(
            endpoint=self._endpoint, index_name=self.index_name, credential=self._credential
        )
        return self._client

    async def healthy(self) -> bool:
        try:
            client = self._ensure_client()
            await client.get_document_count()
        except Exception:
            return False
        return True

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    @staticmethod
    def entitlement_filter(query: RetrievalQuery) -> str:
        """OData filter restricting results to the caller's groups and classification.

        Empty entitlements produce a filter that matches nothing, which is the
        correct interpretation of "entitled to nothing".
        """
        if not query.entitlement_groups:
            return "search.in(access_groups, '', ',')"
        escaped = ",".join(sorted(g.replace("'", "''") for g in query.entitlement_groups))
        permitted = [c.value for c in Classification if c.rank <= query.max_classification.rank]
        classifications = ",".join(permitted)
        return (
            f"access_groups/any(group: search.in(group, '{escaped}', ',')) "
            f"and search.in(classification, '{classifications}', ',')"
        )

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        started = time.perf_counter()
        client = self._ensure_client()

        kwargs: dict[str, Any] = {
            "search_text": query.text,
            "filter": self.entitlement_filter(query),
            "top": query.top_k,
            "select": list(SELECT_FIELDS),
        }
        if query.strategy in {RetrievalStrategy.SEMANTIC, RetrievalStrategy.HYBRID}:
            kwargs["query_type"] = "semantic"
            kwargs["semantic_configuration_name"] = self._semantic_configuration
        if query.strategy in {RetrievalStrategy.VECTOR, RetrievalStrategy.HYBRID} and self._embed:
            from azure.search.documents.models import VectorizedQuery  # noqa: PLC0415

            vector = await self._embed(query.text)
            kwargs["vector_queries"] = [
                VectorizedQuery(
                    vector=list(vector),
                    # Over-fetch, then let ranking cut: the cheapest available
                    # improvement in retrieval quality.
                    k_nearest_neighbors=query.top_k * 4,
                    fields="content_vector",
                )
            ]

        try:
            results = await client.search(**kwargs)
            items = tuple([self._to_item(entry) async for entry in results])
        except Exception as exc:
            # Never widen the query on failure. An empty result is safe; a
            # broader one is a security incident.
            raise RetrievalUnavailableError(
                f"Azure AI Search query failed: {type(exc).__name__}",
                correlation_id=query.correlation_id,
            ) from exc

        return RetrievalResult(
            query_id=query.query_id,
            correlation_id=query.correlation_id,
            strategy=query.strategy,
            items=items,
            subqueries=(query.text,),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            index_name=self.index_name,
            index_version=self.index_version,
        )

    @staticmethod
    def _to_item(entry: dict[str, Any]) -> RetrievedItem:
        sanitised = sanitise_untrusted(str(entry["passage"]))
        groups = entry.get("access_groups") or []
        return RetrievedItem(
            source_id=str(entry["source_id"]),
            source_title=str(entry.get("source_title", "")),
            passage=sanitised.text,
            source_uri=str(entry.get("source_uri", "")),
            version=str(entry.get("version", "unknown")),
            updated_at=datetime.fromisoformat(str(entry["updated_at"])),
            classification=Classification(entry.get("classification", "internal")),
            access_groups=frozenset(str(g) for g in groups),
            authority=str(entry.get("authority", "secondary")),
            score=float(entry.get("@search.score", 0.0)),
            citation_ref=str(entry["source_id"]),
        )
