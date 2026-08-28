"""Azure Service Bus transport.

Publish-only by design: the worker consumes with the SDK's own receiver so that
prefetch, lock renewal and dead-lettering stay with the library that
understands them, rather than being half-reimplemented here.

The SDK is an optional extra. Its absence is a configuration error with a clear
message, not an import traceback at publish time.
"""

from __future__ import annotations

import logging
from typing import Any

from contracts.errors import UpstreamUnavailableError
from contracts.events import EventEnvelope, EventType

logger = logging.getLogger(__name__)


class ServiceBusEventBus:
    """Publishes envelopes to a Service Bus topic.

    Duplicate detection is configured on the topic (see
    ``infra/bicep/modules/servicebus.bicep``) and keyed on the envelope's
    idempotency key, so a retried publish does not produce a second fact.
    """

    def __init__(
        self,
        *,
        fully_qualified_namespace: str,
        topic_name: str,
        credential: Any,
        client: Any | None = None,
    ) -> None:
        self._namespace = fully_qualified_namespace
        self._topic = topic_name
        self._credential = credential
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from azure.servicebus.aio import ServiceBusClient  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise UpstreamUnavailableError(
                "azure-servicebus is not installed; run `uv sync --extra azure`"
            ) from exc
        self._client = ServiceBusClient(
            fully_qualified_namespace=self._namespace, credential=self._credential
        )
        return self._client

    def subscribe(self, event_type: EventType, handler: Any) -> None:
        raise NotImplementedError("ServiceBusEventBus is publish-only; consume with apps/worker")

    async def publish(self, envelope: EventEnvelope) -> None:
        try:
            from azure.servicebus import ServiceBusMessage  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise UpstreamUnavailableError(
                "azure-servicebus is not installed; run `uv sync --extra azure`"
            ) from exc

        client = self._ensure_client()
        message = ServiceBusMessage(
            body=envelope.model_dump_json(),
            content_type="application/json",
            subject=envelope.event_type.value,
            correlation_id=envelope.correlation_id,
            message_id=envelope.idempotency_key,
            application_properties={
                "schema_version": envelope.schema_version,
                "classification": envelope.classification.value,
                "producer": envelope.producer,
            },
        )
        async with client.get_topic_sender(topic_name=self._topic) as sender:
            await sender.send_messages(message)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
