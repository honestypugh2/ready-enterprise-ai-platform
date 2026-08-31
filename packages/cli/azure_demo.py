"""Stage operations for the live Azure demonstration.

These commands prepare and inspect cloud dependencies. They do not change the
platform's default mode and they do not turn configuration into a proof claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from contracts.common import utcnow
from platform_config import ExecutionMode, PlatformSettings
from retrieval import AzureSearchRetriever, build_retriever
from security.identity import WorkloadIdentity, resolve_credential


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    ok: bool
    evidence: str


def load_demo_documents(
    knowledge_dir: Path, *, include_adversarial: bool = False, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Load synthetic passages in the shape expected by Azure AI Search."""
    observed_at = now or utcnow()
    documents: list[dict[str, Any]] = []
    for path in sorted(knowledge_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("corpus_id") == "adversarial-corpus" and not include_adversarial:
            continue
        for passage in payload.get("passages", []):
            updated_at = observed_at - timedelta(days=int(passage["age_days"]))
            documents.append(
                {
                    "source_id": passage["source_id"],
                    "source_title": passage["source_title"],
                    "passage": passage["passage"],
                    "source_uri": passage["source_uri"],
                    "version": passage["version"],
                    "updated_at": updated_at.isoformat(),
                    "classification": passage.get("classification", "internal"),
                    "access_groups": passage["access_groups"],
                    "authority": passage.get("authority", "secondary"),
                    "freshness_slo_days": passage.get("freshness_slo_days", 90),
                }
            )
    if not documents:
        raise ValueError(f"no demonstration passages found in {knowledge_dir}")
    return documents


def _index_definition(index_name: str) -> Any:
    try:
        from azure.search.documents.indexes.models import (  # noqa: PLC0415
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SemanticConfiguration,
            SemanticField,
            SemanticPrioritizedFields,
            SemanticSearch,
            SimpleField,
        )
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("run `uv sync --extra azure` before indexing Azure AI Search") from exc

    return SearchIndex(
        name=index_name,
        fields=[
            SimpleField(name="source_id", type=cast(Any, SearchFieldDataType.String), key=True),
            SearchField(
                name="source_title",
                type=cast(Any, SearchFieldDataType.String),
                searchable=True,
            ),
            SearchField(
                name="passage", type=cast(Any, SearchFieldDataType.String), searchable=True
            ),
            SimpleField(name="source_uri", type=cast(Any, SearchFieldDataType.String)),
            SimpleField(
                name="version", type=cast(Any, SearchFieldDataType.String), filterable=True
            ),
            SimpleField(
                name="updated_at",
                type=cast(Any, SearchFieldDataType.DateTimeOffset),
                filterable=True,
                sortable=True,
            ),
            SimpleField(
                name="classification",
                type=cast(Any, SearchFieldDataType.String),
                filterable=True,
            ),
            SearchField(
                name="access_groups",
                type=cast(
                    Any,
                    SearchFieldDataType.Collection(  # type: ignore[operator]
                        SearchFieldDataType.String
                    ),
                ),
                filterable=True,
            ),
            SimpleField(
                name="authority", type=cast(Any, SearchFieldDataType.String), filterable=True
            ),
            SimpleField(
                name="freshness_slo_days",
                type=cast(Any, SearchFieldDataType.Int32),
                filterable=True,
            ),
        ],
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="default",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="source_title"),
                        content_fields=[SemanticField(field_name="passage")],
                    ),
                )
            ]
        ),
    )


def index_demo_corpus(
    settings: PlatformSettings, *, include_adversarial: bool = False
) -> tuple[int, str]:
    """Create or update the demo index and upload its synthetic corpus."""
    if settings.mode is ExecutionMode.LOCAL_MOCK:
        raise ValueError("Azure indexing requires REAP_MODE=azure_dev")
    if not settings.retrieval.search_endpoint:
        raise ValueError("REAP_RETRIEVAL_SEARCH_ENDPOINT is required")

    try:
        from azure.search.documents import SearchClient  # noqa: PLC0415
        from azure.search.documents.indexes import SearchIndexClient  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("run `uv sync --extra azure` before indexing Azure AI Search") from exc

    credential = cast(Any, resolve_credential(settings, identity=WorkloadIdentity.RETRIEVAL_CLIENT))
    endpoint = settings.retrieval.search_endpoint
    assert endpoint is not None
    index_name = settings.retrieval.index_name
    SearchIndexClient(endpoint=endpoint, credential=credential).create_or_update_index(
        _index_definition(index_name)
    )
    documents = load_demo_documents(
        settings.retrieval.knowledge_dir, include_adversarial=include_adversarial
    )
    results = SearchClient(
        endpoint=endpoint, index_name=index_name, credential=credential
    ).upload_documents(documents)
    failed = [result.key for result in results if not result.succeeded]
    if failed:
        raise RuntimeError(f"Azure AI Search rejected documents: {failed}")
    return len(documents), index_name


async def run_preflight(settings: PlatformSettings) -> list[PreflightCheck]:
    """Observe stage prerequisites without claiming the full scenario passed."""
    checks = [
        PreflightCheck("azure mode", settings.azure_enabled, settings.mode.value),
        PreflightCheck(
            "retrieval provider",
            settings.retrieval.provider == "azure_search",
            settings.retrieval.provider,
        ),
        PreflightCheck(
            "reasoning provider",
            settings.reasoning.provider in {"foundry", "model_router"},
            settings.reasoning.provider,
        ),
        PreflightCheck(
            "telemetry configured",
            bool(settings.observability.applicationinsights_connection_string),
            "connection string present"
            if settings.observability.applicationinsights_connection_string
            else "missing REAP_OTEL_APPLICATIONINSIGHTS_CONNECTION_STRING",
        ),
        PreflightCheck(
            "writer remains dry run",
            settings.connector.dry_run,
            f"dry_run={settings.connector.dry_run}",
        ),
    ]
    if not settings.azure_enabled:
        return checks

    try:
        credential = cast(
            Any, resolve_credential(settings, identity=WorkloadIdentity.RETRIEVAL_CLIENT)
        )
        credential.get_token("https://search.azure.com/.default")
        checks.append(PreflightCheck("Azure credential", True, "Search token acquired"))
    except Exception as exc:
        checks.append(PreflightCheck("Azure credential", False, type(exc).__name__))
        return checks

    if settings.retrieval.provider == "azure_search":
        retriever = build_retriever(settings, credential=credential)
        try:
            checks.append(
                PreflightCheck(
                    "Azure AI Search",
                    await retriever.healthy(),
                    f"index={settings.retrieval.index_name}",
                )
            )
        finally:
            if isinstance(retriever, AzureSearchRetriever):
                await retriever.close()
    return checks
