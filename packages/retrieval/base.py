"""Retriever protocol.

Entitlements are a required argument, not an optional filter. A retriever that
can be called without them will eventually be called without them.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contracts.errors import UpstreamUnavailableError
from contracts.retrieval import RetrievalQuery, RetrievalResult


class RetrievalUnavailableError(UpstreamUnavailableError):
    """Retrieval failed. The caller must refuse rather than answer ungrounded."""

    plane = "retrieval"


@runtime_checkable
class Retriever(Protocol):
    index_name: str
    index_version: str

    async def search(self, query: RetrievalQuery) -> RetrievalResult: ...
    async def healthy(self) -> bool: ...
