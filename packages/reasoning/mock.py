"""Deterministic mock reasoner.

Composes an explanation by quoting the retrieved evidence. Same evidence always
produces the same wording, so the demo is repeatable and the citation-validation
tests have a stable subject.

It is a template engine, not a model. It exists so the *architecture* around
reasoning — grounding, citation validation, refusal, structured output — is
demonstrable without a model endpoint.
"""

from __future__ import annotations

import asyncio
import time

from contracts.reasoning import Citation, ProposedAction, ReasoningRequest, Recommendation
from contracts.retrieval import RetrievedItem
from contracts.taxonomy import DEFECT_TAXONOMY
from reasoning.base import UngroundedOutputError
from reasoning.prompts import PROMPT_ID, PROMPT_VERSION

_ACTION_BY_SEVERITY = {
    "critical": ("quarantine_batch", "Quarantine the affected batch and hold the line"),
    "major": ("create_work_order", "Raise a maintenance work order against the station"),
    "minor": ("create_work_order", "Raise a station realignment work order"),
    "cosmetic": ("notify_supervisor", "Record the finding for weekly quality review"),
    "none": ("notify_supervisor", "No action required; record the pass"),
}


class MockReasoner:
    """Evidence-quoting explanation generator."""

    model_name = "deterministic-explainer"
    model_version = "1.2.0"
    route_id = "mock-reasoner"

    def __init__(self, *, simulated_latency_ms: float = 12.0, fail_next: bool = False) -> None:
        self._latency_ms = simulated_latency_ms
        self.fail_next = fail_next

    async def healthy(self) -> bool:
        return True

    async def explain(self, request: ReasoningRequest) -> Recommendation:
        if self.fail_next:
            self.fail_next = False
            raise UngroundedOutputError("simulated reasoning failure")

        started = time.perf_counter()
        await asyncio.sleep(self._latency_ms / 1000.0)

        detection = request.detection
        evidence = request.evidence.items

        if not evidence:
            # No evidence means refuse. Missing evidence produces an explicit
            # escalation, not a plausible sentence.
            return self._refusal(
                request,
                started,
                "No governed evidence was retrieved for this detection, so no "
                "grounded explanation can be produced.",
            )

        primary = self._best_evidence(evidence)
        taxonomy = DEFECT_TAXONOMY.get(detection.primary_label)
        severity_key = taxonomy.default_severity.value if taxonomy else "minor"
        display = taxonomy.display_name if taxonomy else detection.primary_label

        # Cite only what is actually quoted. Citing every retrieved passage
        # inflates the count and fails citation validation for the right reason.
        cited = [primary]
        supporting = next(
            (item for item in evidence if item.citation_ref != primary.citation_ref), None
        )
        if supporting is not None:
            cited.append(supporting)

        citations = tuple(
            Citation(
                citation_ref=item.citation_ref,
                source_id=item.source_id,
                source_title=item.source_title,
                source_uri=item.source_uri,
                quoted_span=self._first_sentence(item.passage),
                supports_claim=self._first_sentence(item.passage),
            )
            for item in cited
        )

        missing = self._missing_information(request, evidence)
        action_kind, action_summary = _ACTION_BY_SEVERITY.get(
            severity_key, ("notify_supervisor", "Record the finding")
        )

        headline = (
            f"{display} detected at {detection.primary_confidence:.0%} confidence "
            f"(threshold {detection.decision_threshold:.0%})"
        )
        rationale = (
            f"The detector reported {display} at {detection.primary_confidence:.2%} confidence "
            f"against a decision threshold of {detection.decision_threshold:.2%} [detection]. "
            f"{self._cite(primary)} "
            + (f"{self._cite(supporting)} " if supporting is not None else "")
            + "Disposition, approval and permitted actions come from the platform policy "
            "engine, not from this explanation."
        )

        return Recommendation(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            headline=headline,
            rationale=rationale,
            proposed_action=ProposedAction(
                action_kind=action_kind,
                target_system="mock-erp",
                summary=action_summary,
                parameters=(
                    ("defect_label", detection.primary_label),
                    ("prediction_id", detection.prediction_id),
                ),
            ),
            citations=citations,
            missing_information=missing,
            self_reported_confidence=round(min(0.9, detection.primary_confidence), 4),
            model_name=self.model_name,
            model_version=self.model_version,
            prompt_id=PROMPT_ID,
            prompt_version=PROMPT_VERSION,
            route_id=self.route_id,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _best_evidence(evidence: tuple[RetrievedItem, ...]) -> RetrievedItem:
        authoritative = [item for item in evidence if item.authority == "authoritative"]
        return (authoritative or list(evidence))[0]

    @staticmethod
    def _first_sentence(passage: str, *, limit: int = 400) -> str:
        head = passage.split(". ")[0].strip().rstrip(".")
        return head[:limit]

    @classmethod
    def _cite(cls, item: RetrievedItem) -> str:
        """Quote a passage with its marker inside the sentence it supports."""
        return f"{cls._first_sentence(item.passage)} [{item.citation_ref}]."

    @staticmethod
    def _missing_information(
        request: ReasoningRequest, evidence: tuple[RetrievedItem, ...]
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not any(item.authority == "authoritative" for item in evidence):
            missing.append(
                "No authoritative standard was retrieved; only secondary or reference material."
            )
        stale = [item.citation_ref for item in evidence if item.is_stale()]
        if stale:
            missing.append(
                f"Evidence past its freshness SLO was retrieved: {', '.join(sorted(stale))}."
            )
        if request.evidence.partial:
            missing.append("Retrieval returned a partial result; some sources were not reachable.")
        return tuple(missing)

    def _refusal(self, request: ReasoningRequest, started: float, reason: str) -> Recommendation:
        return Recommendation(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            headline="Unable to produce a grounded explanation",
            rationale=reason,
            proposed_action=None,
            citations=(),
            missing_information=("No retrievable evidence for this detection.",),
            self_reported_confidence=0.0,
            refused=True,
            refusal_reason=reason,
            model_name=self.model_name,
            model_version=self.model_version,
            prompt_id=PROMPT_ID,
            prompt_version=PROMPT_VERSION,
            route_id=self.route_id,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
