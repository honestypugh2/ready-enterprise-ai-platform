"""Data and knowledge plane.

Retrieval is a governed data product, not a feature of the chat window. Every
passage carries authority, entitlement, freshness and a citation reference, so a
downstream component can refuse to use it rather than discovering the problem in
an answer.

Two rules this plane enforces rather than documents:

* Entitlement is applied **at query time**, server side. Post-filtering leaks
  both content and the existence of content.
* Retrieved text is untrusted input and is sanitised before it leaves the
  retriever.
"""

from retrieval.agentic import AgenticRetriever, deterministic_planner
from retrieval.azure_search import AzureSearchRetriever
from retrieval.base import RetrievalUnavailableError, Retriever
from retrieval.citations import (
    DETECTION_REF,
    CitationIssue,
    CitationReport,
    support_score,
    validate_citations,
)
from retrieval.factory import build_retriever
from retrieval.local import LocalKnowledgeRetriever

__all__ = [
    "DETECTION_REF",
    "AgenticRetriever",
    "AzureSearchRetriever",
    "CitationIssue",
    "CitationReport",
    "LocalKnowledgeRetriever",
    "RetrievalUnavailableError",
    "Retriever",
    "build_retriever",
    "deterministic_planner",
    "support_score",
    "validate_citations",
]
