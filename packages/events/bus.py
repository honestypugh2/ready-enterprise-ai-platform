"""In-process event bus.

Idempotency is enforced at the bus, not in each handler: a duplicate envelope
is dropped once rather than being defended against in nine places. That is the
same guarantee Service Bus duplicate detection provides, implemented locally so
the two modes behave the same way.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from contracts.events import EventEnvelope, EventType

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None: ...
    async def close(self) -> None: ...


class InMemoryEventBus:
    """Deterministic, ordered, at-most-once delivery within one process."""

    def __init__(self, *, dedupe_window: int = 4096) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._seen: dict[str, None] = {}
        self._dedupe_window = dedupe_window
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, envelope: EventEnvelope) -> None:
        async with self._lock:
            if envelope.idempotency_key in self._seen:
                logger.debug(
                    "duplicate_event_suppressed",
                    extra={
                        "event_type": envelope.event_type.value,
                        "correlation_id": envelope.correlation_id,
                    },
                )
                return
            self._seen[envelope.idempotency_key] = None
            if len(self._seen) > self._dedupe_window:
                # Bounded memory: drop the oldest key. Insertion order is
                # guaranteed for dict in CPython 3.7+.
                oldest = next(iter(self._seen))
                del self._seen[oldest]

        for handler in self._handlers[envelope.event_type]:
            try:
                await handler(envelope)
            except Exception:
                # A failing subscriber degrades that subscriber, not the
                # transaction that published the fact.
                logger.exception(
                    "event_handler_failed",
                    extra={
                        "event_type": envelope.event_type.value,
                        "correlation_id": envelope.correlation_id,
                    },
                )

    async def close(self) -> None:
        self._handlers.clear()


class RecordingEventBus(InMemoryEventBus):
    """Test double that keeps every published envelope in order."""

    def __init__(self) -> None:
        super().__init__()
        self.published: list[EventEnvelope] = []

    async def publish(self, envelope: EventEnvelope) -> None:
        self.published.append(envelope)
        await super().publish(envelope)

    def types(self) -> tuple[EventType, ...]:
        return tuple(e.event_type for e in self.published)

    def of_type(self, event_type: EventType) -> tuple[EventEnvelope, ...]:
        return tuple(e for e in self.published if e.event_type is event_type)
