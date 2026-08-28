"""OpenTelemetry setup and the span vocabulary the whole platform shares.

Span names follow the workflow's own step vocabulary, so a trace reads the way
the architecture diagram is drawn. Attributes carry identifiers, versions,
counts and decisions — never payload content. Full content lives in the
evidence store, where access is controlled and retention is enforced.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from platform_config import PlatformSettings
from security.redaction import REDACTED, SENSITIVE_KEYS, redact_value

logger = logging.getLogger(__name__)

TRACER_NAME = "ready_enterprise_ai_platform"

_configured = False


def configure_observability(settings: PlatformSettings) -> None:
    """Idempotent tracer setup. Safe to call from every entry point."""
    global _configured
    if _configured:
        return

    resource = Resource.create(
        {
            "service.name": settings.observability.service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
            "reap.workload_id": settings.workload_id,
            "reap.mode": settings.mode.value,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.observability.sample_ratio)),
    )

    connection_string = settings.observability.applicationinsights_connection_string
    if connection_string:
        try:
            from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415
                AzureMonitorTraceExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(AzureMonitorTraceExporter(connection_string=connection_string))
            )
        except ImportError:  # pragma: no cover - depends on optional extra
            logger.warning(
                "application_insights_configured_but_exporter_missing; run `uv sync --extra azure`"
            )

    if settings.observability.console_exporter and not connection_string:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _configured = True


def reset_observability() -> None:
    """Test hook."""
    global _configured
    _configured = False


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME)


def _safe_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Scalars only, redacted by key and by value pattern."""
    result: dict[str, Any] = {}
    for key, value in attributes.items():
        if key.lower() in SENSITIVE_KEYS:
            result[key] = REDACTED
        elif isinstance(value, bool | int | float):
            result[key] = value
        else:
            result[key] = redact_value(value)
    return result


@contextmanager
def traced_step(
    name: str,
    *,
    correlation_id: str,
    attributes: Mapping[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Iterator[Span]:
    """Trace one step of the reference flow.

    Use the workflow's step vocabulary for ``name``: detect, retrieve, route,
    reason, validate, supervise, act, observe.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind) as span:
        span.set_attribute("reap.correlation_id", correlation_id)
        for key, value in _safe_attributes(attributes or {}).items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            span.record_exception(exc)
            raise
        span.set_status(Status(StatusCode.OK))


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None
