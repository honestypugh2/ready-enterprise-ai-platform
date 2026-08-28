"""Human-in-the-loop approval contracts.

The approver sees evidence, the proposed action, the authoritative values, the
policy result and the expected downstream effect. A natural-language summary
alone is not an approval surface.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.common import PlatformModel, new_id, utcnow


class ApprovalState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"
    REVOKED = "revoked"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {
            ApprovalState.APPROVED,
            ApprovalState.REJECTED,
            ApprovalState.EXPIRED,
            ApprovalState.REVOKED,
            ApprovalState.FAILED,
            ApprovalState.NOT_REQUIRED,
        }

    @property
    def permits_write(self) -> bool:
        return self in {ApprovalState.APPROVED, ApprovalState.MODIFIED}


class ApprovalEvidence(PlatformModel):
    """The five things an approval screen must show, as data rather than prose."""

    citations: tuple[str, ...]
    authoritative_values: tuple[tuple[str, str], ...]
    policy_reason_codes: tuple[str, ...]
    expected_downstream_effect: str = Field(min_length=1, max_length=500)
    detection_summary: str = Field(min_length=1, max_length=500)


class ApprovalRequest(PlatformModel):
    """A request for a decision, bound to an exact proposal fingerprint."""

    approval_id: str = Field(default_factory=lambda: new_id("apr"))
    correlation_id: str
    policy_decision_id: str
    proposal_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    requested_by: str = Field(min_length=1, max_length=128)
    required_role: str = Field(min_length=1, max_length=64)
    dual_control_required: bool = False
    proposed_action_summary: str = Field(min_length=1, max_length=500)
    evidence: ApprovalEvidence

    requested_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime

    @model_validator(mode="after")
    def _expiry_in_future(self) -> Self:
        if self.expires_at <= self.requested_at:
            raise ValueError("expires_at must be after requested_at")
        return self

    @classmethod
    def default_expiry(cls, *, hours: int = 8, now: datetime | None = None) -> datetime:
        return (now or utcnow()) + timedelta(hours=hours)


class ApprovalDecision(PlatformModel):
    """One approver's verdict."""

    approver_principal_id: str = Field(min_length=1, max_length=128)
    approver_role: str = Field(min_length=1, max_length=64)
    state: ApprovalState
    rationale: str = Field(min_length=1, max_length=1_000)
    modified_payload: tuple[tuple[str, str], ...] = ()
    decided_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _modified_requires_payload(self) -> Self:
        if self.state is ApprovalState.MODIFIED and not self.modified_payload:
            raise ValueError("a modified approval must carry the modified payload")
        if self.state in {ApprovalState.PENDING, ApprovalState.NOT_REQUIRED}:
            raise ValueError("a decision cannot be pending or not_required")
        return self


class ApprovalRecord(PlatformModel):
    """The persisted approval, which is the artifact the writer verifies."""

    approval_id: str
    correlation_id: str
    policy_decision_id: str
    proposal_fingerprint: str
    state: ApprovalState
    request: ApprovalRequest
    decisions: tuple[ApprovalDecision, ...] = ()
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def effective_payload(self) -> tuple[tuple[str, str], ...] | None:
        for decision in reversed(self.decisions):
            if decision.state is ApprovalState.MODIFIED:
                return decision.modified_payload
        return None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or utcnow()) >= self.request.expires_at

    @model_validator(mode="after")
    def _dual_control(self) -> Self:
        if self.state.permits_write and self.request.dual_control_required:
            approvers = {d.approver_principal_id for d in self.decisions if d.state.permits_write}
            if len(approvers) < 2:
                raise ValueError("dual control requires two distinct approving principals")
        return self
