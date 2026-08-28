"""Observability plane.

One trace spans detection through action, joined by a correlation id. Quality
and action are first-class signals alongside latency and errors, because the
most damaging failure mode in this architecture produces no errors at all.

Telemetry records shape and decision; the evidence store records content.
"""

from observability.logging_config import StructuredFormatter, configure_logging, get_logger
from observability.metrics import METRICS, WorkloadMetrics
from observability.tracing import (
    TRACER_NAME,
    configure_observability,
    current_trace_id,
    get_tracer,
    reset_observability,
    traced_step,
)

__all__ = [
    "METRICS",
    "TRACER_NAME",
    "StructuredFormatter",
    "WorkloadMetrics",
    "configure_logging",
    "configure_observability",
    "current_trace_id",
    "get_logger",
    "get_tracer",
    "reset_observability",
    "traced_step",
]
