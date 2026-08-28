"""Policy contracts: the deterministic verdict that reasoning may explain but never change."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.action import ActionKind
from contracts.common import PlatformModel, new_id, utcnow
from contracts.detection import DetectionSeverity


class Disposition(StrEnum):
    """What the business does with the unit and the signal."""

    NO_ACTION = "no_action"
    LOG_ONLY = "log_only"
    RE_INSPECT = "re_inspect"
    QUARANTINE = "quarantine"
    MAINTENANCE_WORK_ORDER = "maintenance_work_order"
    STOP_LINE = "stop_line"


class PolicyObligation(PlatformModel):
    """A condition the rest of the flow must satisfy before acting."""

    obligation_id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=300)
    satisfied_by: str = Field(min_length=1, max_length=64)


class PolicyDecision(PlatformModel):
    """The authoritative verdict.

    Produced by versioned rules executing in code. Reproducible from the same
    inputs and the same policy version, which is what makes it replayable in an
    evaluation harness and defensible in a review.
    """

    decision_id: str = Field(default_factory=lambda: new_id("pol"))
    correlation_id: str
    prediction_id: str

    allowed: bool
    severity: DetectionSeverity
    disposition: Disposition
    permitted_actions: tuple[ActionKind, ...] = ()
    approval_required: bool
    approver_role: str | None = Field(default=None, max_length=64)
    dual_control_required: bool = False

    reason_codes: tuple[str, ...]
    matched_rules: tuple[str, ...]
    obligations: tuple[PolicyObligation, ...] = ()

    policy_version: str = Field(min_length=1, max_length=32)
    policy_sha: str = Field(min_length=8, max_length=80)
    evaluated_at: datetime = Field(default_factory=utcnow)
    evaluation_ms: float = Field(ge=0.0, default=0.0)

    @model_validator(mode="after")
    def _consistency(self) -> Self:
        if not self.reason_codes:
            raise ValueError("a policy decision must carry at least one reason code")
        if not self.allowed and self.permitted_actions:
            raise ValueError("a denied decision cannot permit actions")
        if self.approval_required and not self.approver_role:
            raise ValueError("an approval requirement must name the approving role")
        if self.dual_control_required and not self.approval_required:
            raise ValueError("dual control implies approval is required")
        return self
