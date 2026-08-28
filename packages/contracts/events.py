"""Versioned event envelope.

The envelope is deliberately transport-neutral: the same payload is carried by
an in-process bus in local mode, by Azure Service Bus in Azure mode, and maps
onto the CloudEvents fields Event Grid expects. Consumers bind to the envelope,
not to the broker.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from contracts.common import (
    CONTRACT_VERSION,
    Classification,
    PlatformModel,
    content_hash,
    new_id,
    utcnow,
)


class EventType(StrEnum):
    """The twelve facts the reference workflow publishes about itself."""

    PREDICTION_CREATED = "reap.prediction.created.v1"
    CONTEXT_RETRIEVED = "reap.context.retrieved.v1"
    ROUTE_SELECTED = "reap.route.selected.v1"
    RECOMMENDATION_GENERATED = "reap.recommendation.generated.v1"
    POLICY_EVALUATED = "reap.policy.evaluated.v1"
    APPROVAL_REQUESTED = "reap.approval.requested.v1"
    APPROVAL_DECIDED = "reap.approval.decided.v1"
    ACTION_EXECUTED = "reap.action.executed.v1"
    ACTION_FAILED = "reap.action.failed.v1"
    EVALUATION_COMPLETED = "reap.evaluation.completed.v1"
    AUDIT_SEALED = "reap.audit.sealed.v1"
    KILL_SWITCH_ENGAGED = "reap.operations.killswitch.v1"


class EventEnvelope(PlatformModel):
    """Envelope carrying one fact plus the metadata that makes it replayable."""

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: EventType
    schema_version: str = CONTRACT_VERSION

    correlation_id: str
    causation_id: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)

    producer: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    classification: Classification = Classification.INTERNAL
    occurred_at: datetime = Field(default_factory=utcnow)

    payload: dict[str, Any]
    payload_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @classmethod
    def create(
        cls,
        *,
        event_type: EventType,
        correlation_id: str,
        producer: str,
        subject: str,
        payload: dict[str, Any],
        causation_id: str | None = None,
        idempotency_key: str | None = None,
        classification: Classification = Classification.INTERNAL,
    ) -> EventEnvelope:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = content_hash(canonical.encode("utf-8"))
        return cls(
            event_type=event_type,
            correlation_id=correlation_id,
            causation_id=causation_id,
            idempotency_key=idempotency_key or f"{correlation_id}:{event_type.value}",
            producer=producer,
            subject=subject,
            classification=classification,
            payload=payload,
            payload_hash=digest,
        )

    def to_cloud_event(self) -> dict[str, Any]:
        """CloudEvents 1.0 projection for Event Grid-compatible transports."""
        return {
            "specversion": "1.0",
            "id": self.event_id,
            "source": f"/reap/{self.producer}",
            "type": self.event_type.value,
            "subject": self.subject,
            "time": self.occurred_at.isoformat(),
            "datacontenttype": "application/json",
            "dataschema": f"reap://contracts/{self.schema_version}",
            "data": self.payload,
            "correlationid": self.correlation_id,
            "causationid": self.causation_id,
        }

    @model_validator(mode="after")
    def _payload_hash_matches(self) -> Self:
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str)
        if content_hash(canonical.encode("utf-8")) != self.payload_hash:
            raise ValueError("payload_hash does not match payload")
        return self
