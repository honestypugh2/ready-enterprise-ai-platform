"""Retriever selection."""

from __future__ import annotations

from typing import Any

from platform_config import ExecutionMode, PlatformSettings
from retrieval.base import RetrievalUnavailableError, Retriever
from retrieval.local import LocalKnowledgeRetriever


def build_retriever(settings: PlatformSettings, *, credential: Any | None = None) -> Retriever:
    config = settings.retrieval

    if config.provider == "local":
        return LocalKnowledgeRetriever(
            knowledge_dir=config.knowledge_dir,
            index_name=config.index_name,
        )

    if config.provider == "azure_search":
        if settings.mode is ExecutionMode.LOCAL_MOCK:
            raise RetrievalUnavailableError(
                "provider=azure_search requires REAP_MODE=azure_dev or production"
            )
        from retrieval.azure_search import AzureSearchRetriever  # noqa: PLC0415

        if not config.search_endpoint:
            raise RetrievalUnavailableError(
                "REAP_RETRIEVAL_SEARCH_ENDPOINT must be set when provider=azure_search"
            )
        return AzureSearchRetriever(
            endpoint=config.search_endpoint,
            index_name=config.index_name,
            credential=credential,
            semantic_configuration=config.semantic_configuration,
        )

    raise RetrievalUnavailableError(f"unknown retrieval provider: {config.provider}")
