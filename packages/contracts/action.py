"""Enterprise action contracts.

One component performs mutations. Everything else proposes. The
``ActionRequest`` therefore requires an ``approval_id`` and a
``proposal_fingerprint``: the writer will not execute a proposal that differs
by a single byte from the one a human agreed to.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.common import PlatformModel, new_id, utcnow


class ActionKind(StrEnum):
    """Every mutation the platform is capable of proposing."""

    CREATE_WORK_ORDER = "create_work_order"
    CREATE_INCIDENT = "create_incident"
    QUARANTINE_BATCH = "quarantine_batch"
    SCHEDULE_INSPECTION = "schedule_inspection"
    NOTIFY_SUPERVISOR = "notify_supervisor"
    CREATE_REPLENISHMENT_ORDER = "create_replenishment_order"


class ActionStatus(StrEnum):
    PENDING = "pending"
    DRY_RUN = "dry_run"
    SUCCEEDED = "succeeded"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    FAILED = "failed"
    COMPENSATED = "compensated"


class ActionRequest(PlatformModel):
    """A validated, approved, fingerprinted instruction to mutate a system of record."""

    action_id: str = Field(default_factory=lambda: new_id("act"))
    correlation_id: str
    causation_id: str

    kind: ActionKind
    target_system: str = Field(min_length=1, max_length=64)
    payload: tuple[tuple[str, str], ...]

    # Bindings that make the write defensible.
    approval_id: str = Field(min_length=8, max_length=64)
    proposal_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_decision_id: str = Field(min_length=8, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)

    dry_run: bool = True
    timeout_ms: int = Field(default=10_000, gt=0, le=120_000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    requested_at: datetime = Field(default_factory=utcnow)

    def payload_dict(self) -> dict[str, str]:
        return dict(self.payload)


class ActionReceipt(PlatformModel):
    """Proof of what happened, including proof that nothing happened."""

    receipt_id: str = Field(default_factory=lambda: new_id("rcpt"))
    action_id: str
    correlation_id: str
    status: ActionStatus
    target_system: str
    external_reference: str | None = None
    attempts: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    error_code: str | None = None
    error_detail: str | None = Field(default=None, max_length=500)
    compensation_of: str | None = None
    executed_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _status_consistency(self) -> Self:
        if self.status is ActionStatus.SUCCEEDED and not self.external_reference:
            raise ValueError("a successful write must return an external reference")
        if self.status is ActionStatus.FAILED and not self.error_code:
            raise ValueError("a failed write must carry an error code")
        return self
