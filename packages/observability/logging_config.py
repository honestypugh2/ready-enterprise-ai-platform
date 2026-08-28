"""Structured JSON logging.

Logs are emitted as structured events with the correlation id, the component,
the acting identity and the outcome — never as free text assembled from string
concatenation, because the point of the log is to be queried rather than read.

Redaction happens in the formatter, so a caller cannot bypass it by logging an
unusual field.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

from observability.tracing import current_trace_id
from security.redaction import redact_attributes

_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class StructuredFormatter(logging.Formatter):
    """Renders one JSON object per record, redacted and trace-joined."""

    def format(self, record: logging.LogRecord) -> str:
        extras: dict[str, Any] = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED
        }
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
            **redact_attributes(extras),
        }
        trace_id = current_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            # The message, not the traceback: tracebacks can echo payload values.
            payload["exception_message"] = str(record.exc_info[1])
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(*, level: int = logging.INFO) -> None:
    """Replace root handlers with a single structured handler."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Access logs would duplicate the API middleware's structured request event.
    logging.getLogger("uvicorn.access").disabled = True


class _MergingAdapter(logging.LoggerAdapter[logging.Logger]):
    """Merges per-call ``extra`` with the adapter's bound context.

    ``LoggerAdapter.process`` replaces ``kwargs["extra"]`` by default, which
    silently discards the fields the caller passed — structured logging that
    drops its structure. Bound context loses to the call site on a key clash,
    since the call site is the more specific statement.
    """

    def process(
        self, msg: object, kwargs: MutableMapping[str, Any]
    ) -> tuple[object, MutableMapping[str, Any]]:
        bound = dict(self.extra or {})
        bound.update(kwargs.get("extra") or {})
        kwargs["extra"] = bound
        return msg, kwargs

    def bind(self, **fields: Any) -> _MergingAdapter:
        """Return an adapter carrying additional context on every record."""
        return _MergingAdapter(self.logger, {**(self.extra or {}), **fields})


def get_logger(name: str, **context: Any) -> _MergingAdapter:
    return _MergingAdapter(logging.getLogger(name), context)
