"""Correlation, security headers, body limits and a token bucket.

Deliberately hand-written rather than pulled from a middleware library: each of
these is a control that a reviewer should be able to read in full, and the total
is under two hundred lines.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from contracts.common import new_id
from observability import current_trace_id
from observability.logging_config import get_logger

logger = get_logger(__name__)

CORRELATION_HEADER = "x-correlation-id"

# Applied to every response. The API serves JSON only, so the content policy can
# be maximally restrictive without breaking a legitimate caller.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Cache-Control": "no-store",
}


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Accepts an inbound correlation id or mints one, and echoes it back.

    The value is constrained before it is trusted: an unvalidated header ends up
    in logs and traces, which makes it an injection surface.
    """

    _MAX_LENGTH = 64

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get(CORRELATION_HEADER, "")
        correlation_id = (
            supplied
            if supplied.replace("_", "").replace("-", "").isalnum()
            and 8 <= len(supplied) <= self._MAX_LENGTH
            else new_id("corr")
        )
        request.state.correlation_id = correlation_id

        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        response.headers[CORRELATION_HEADER] = correlation_id
        trace_id = current_trace_id()
        if trace_id:
            response.headers["x-trace-id"] = trace_id

        logger.info(
            "http_request",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects oversized bodies before they are parsed.

    A frame is referenced by hash rather than uploaded inline, so a large body
    is either a mistake or an attempt to exhaust the parser.
    """

    def __init__(self, app: object, *, max_bytes: int = 1_048_576) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self._max_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "request_too_large",
                    "detail": f"body exceeds {self._max_bytes} bytes",
                },
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-client limiter.

    In-process and therefore per-replica: this is a demonstration guard, not the
    production control. In Azure the quota lives at the API Management gateway,
    where it applies across every replica and every consumer.
    """

    def __init__(self, app: object, *, requests_per_minute: int = 120) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limit = requests_per_minute
        self._windows: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))

    def _evict_stale(self, window: int) -> None:
        """Drop windows that have rolled over.

        Without this the map grows one entry per distinct client address and
        never shrinks, which is a slow memory leak in the request path and an
        easy one to trigger deliberately.
        """
        stale = [client for client, (seen, _) in self._windows.items() if seen != window]
        for client in stale:
            del self._windows[client]

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in {"/healthz", "/readyz", "/livez"}:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        current_window, count = self._windows[client]

        if current_window != window:
            self._evict_stale(window)
            self._windows[client] = (window, 1)
        elif count >= self._limit:
            logger.warning("rate_limited", extra={"client": client, "limit": self._limit})
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "detail": "too many requests"},
                headers={"Retry-After": "60"},
            )
        else:
            self._windows[client] = (window, count + 1)

        return await call_next(request)
