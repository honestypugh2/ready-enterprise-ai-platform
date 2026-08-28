"""Event plane.

An abstraction over the transport, not a wrapper around one broker. Local mode
uses an in-process bus; Azure mode uses Service Bus; the CloudEvents projection
on the envelope covers Event Grid. Consumers bind to ``EventEnvelope`` and never
to the broker, which makes the transport a deployment decision rather than an
architectural one.
"""

from events.bus import EventBus, EventHandler, InMemoryEventBus, RecordingEventBus
from events.publisher import EventPublisher
from events.servicebus import ServiceBusEventBus

__all__ = [
    "EventBus",
    "EventHandler",
    "EventPublisher",
    "InMemoryEventBus",
    "RecordingEventBus",
    "ServiceBusEventBus",
]
