"""Primitives every other contract builds on: identity, time, classification, cost."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bumped whenever a breaking change is made to any contract in this package.
# Every event, receipt and decision carries it so that a consumer can refuse a
# payload it was not written against instead of silently mis-parsing it.
CONTRACT_VERSION = "1.0.0"

ShortId = Annotated[str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]


def utcnow() -> datetime:
    """Timezone-aware now. The platform never produces a naive timestamp."""
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Prefixed identifier so a bare string in a log is still self-describing."""
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def content_hash(payload: bytes) -> str:
    """Stable digest used for input provenance and duplicate-write detection."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class Classification(StrEnum):
    """Data classification travelling with every payload and retrieved passage.

    Routing, telemetry redaction and residency rules all read this value, so it
    is set at ingestion rather than inferred later.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

    @property
    def rank(self) -> int:
        return {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}[self.value]


class ExecutionLocation(StrEnum):
    """Where a computation physically ran. Required for residency evidence."""

    LOCAL_PROCESS = "local_process"
    EDGE = "edge"
    AZURE_REGIONAL = "azure_regional"
    AZURE_GLOBAL = "azure_global"
    MOCK = "mock"


class CostCategory(StrEnum):
    """Coarse unit-economics band.

    Deliberately a band and not a currency amount: the repository does not know
    a customer's negotiated rate card and must not invent one. Real currency
    only ever appears when a rate card is supplied by configuration.
    """

    NONE = "none"
    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlatformModel(BaseModel):
    """Base for every contract: immutable, strict, and closed to unknown keys."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_assignment=True,
        use_enum_values=False,
        ser_json_timedelta="iso8601",
    )


class CorrelationContext(PlatformModel):
    """The identifiers that let one decision be reconstructed months later.

    ``correlation_id`` spans the whole business transaction. ``causation_id``
    points at the immediately preceding step, which is what makes a fan-out
    reconstructable rather than merely grouped.
    """

    correlation_id: ShortId = Field(default_factory=lambda: new_id("corr"))
    causation_id: str | None = None
    tenant_id: str = "demo-tenant"
    workload_id: str = "manufacturing-quality"
    initiated_by: str = "system"

    def child(self, causation_id: str) -> CorrelationContext:
        return self.model_copy(update={"causation_id": causation_id})


class Provenance(PlatformModel):
    """Who or what produced an artifact, and from which inputs."""

    producer: str
    producer_version: str
    execution_location: ExecutionLocation
    produced_at: datetime = Field(default_factory=utcnow)
    input_hashes: tuple[str, ...] = ()
    policy_version: str | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reject_naive_timestamp(self) -> Self:
        if self.produced_at.tzinfo is None:
            raise ValueError("produced_at must be timezone-aware")
        return self


class LatencyBudget(PlatformModel):
    """A stage's share of the end-to-end budget, plus what to do when it is spent."""

    target_ms: int = Field(gt=0, le=600_000)
    timeout_ms: int = Field(gt=0, le=600_000)
    fallback_allowed: bool = True

    @model_validator(mode="after")
    def _timeout_not_below_target(self) -> Self:
        if self.timeout_ms < self.target_ms:
            raise ValueError("timeout_ms must be >= target_ms")
        return self
