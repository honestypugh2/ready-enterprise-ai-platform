"""Reasoning contracts.

The reasoning plane proposes and explains. It has no field here through which
it could approve, calculate an authoritative value, or name a system of record
to write to. That is enforced by the shape of the contract rather than by an
instruction in a prompt.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from contracts.common import PlatformModel, new_id, utcnow
from contracts.detection import DetectionResult
from contracts.retrieval import RetrievalResult


class Citation(PlatformModel):
    """A claim bound to the passage that supports it."""

    citation_ref: str = Field(min_length=1, max_length=32)
    source_id: str
    source_title: str
    source_uri: str
    quoted_span: str = Field(min_length=1, max_length=1_000)
    supports_claim: str = Field(min_length=1, max_length=1_000)


class ReasoningRequest(PlatformModel):
    """Evidence in, explanation out. The request carries no write capability."""

    request_id: str = Field(default_factory=lambda: new_id("reason"))
    correlation_id: str
    detection: DetectionResult
    evidence: RetrievalResult
    prompt_id: str = Field(min_length=1, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=32)
    max_output_tokens: int = Field(default=800, ge=32, le=8_000)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)


class ProposedAction(PlatformModel):
    """A suggestion. Nothing downstream treats this as an instruction.

    Deterministic policy decides whether the action is permitted at all, and a
    human decides whether it happens. The reasoner only gets to name a shape.
    """

    action_kind: str = Field(min_length=1, max_length=64)
    target_system: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=500)
    parameters: tuple[tuple[str, str], ...] = ()


class Recommendation(PlatformModel):
    """Structured reasoning output. Free text is confined to named fields."""

    recommendation_id: str = Field(default_factory=lambda: new_id("rec"))
    request_id: str
    correlation_id: str

    headline: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=4_000)
    proposed_action: ProposedAction | None = None
    citations: tuple[Citation, ...] = ()
    missing_information: tuple[str, ...] = ()
    self_reported_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    refused: bool = False
    refusal_reason: str | None = Field(default=None, max_length=500)

    model_name: str
    model_version: str
    prompt_id: str
    prompt_version: str
    route_id: str
    latency_ms: float = Field(ge=0.0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    generated_at: datetime = Field(default_factory=utcnow)

    @property
    def is_grounded(self) -> bool:
        return self.refused or len(self.citations) > 0

    @model_validator(mode="after")
    def _refusal_and_grounding(self) -> Recommendation:
        if self.refused:
            if not self.refusal_reason:
                raise ValueError("a refusal must state why")
            if self.proposed_action is not None:
                raise ValueError("a refusal cannot also propose an action")
        elif not self.citations:
            # An ungrounded recommendation is a defect, not a degraded answer.
            raise ValueError(
                "a non-refusing recommendation must cite at least one retrieved passage"
            )
        return self
