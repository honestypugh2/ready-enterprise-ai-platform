"""Typed publishing helpers.

One method per fact the workflow can state. Callers cannot construct an
envelope with the wrong producer, a missing correlation id or an unhashed
payload, because they never construct one directly.
"""

from __future__ import annotations

from typing import Any

from contracts.common import Classification
from contracts.events import EventEnvelope, EventType
from events.bus import EventBus


class EventPublisher:
    """Binds a bus, a producer name and a correlation id together."""

    def __init__(self, bus: EventBus, *, producer: str) -> None:
        self._bus = bus
        self._producer = producer

    async def emit(
        self,
        *,
        event_type: EventType,
        correlation_id: str,
        subject: str,
        payload: dict[str, Any],
        causation_id: str | None = None,
        classification: Classification = Classification.INTERNAL,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope.create(
            event_type=event_type,
            correlation_id=correlation_id,
            producer=self._producer,
            subject=subject,
            payload=payload,
            causation_id=causation_id,
            classification=classification,
            idempotency_key=idempotency_key,
        )
        await self._bus.publish(envelope)
        return envelope
