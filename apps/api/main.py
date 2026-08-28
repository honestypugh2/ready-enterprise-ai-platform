"""FastAPI application.

The API is a thin surface over the workflow. It owns request validation,
identity resolution, correlation and telemetry; every governance decision is
made by the planes underneath it. Anything an operator can do through this API,
the CLI can do through the same objects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.middleware import (
    BodySizeLimitMiddleware,
    CorrelationMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from api.routers import approvals, governance, health, inspections
from api.schemas import ErrorResponse
from contracts.errors import (
    ApprovalRequiredError,
    KillSwitchEngagedError,
    PlatformError,
    PolicyDeniedError,
    UpstreamUnavailableError,
)
from observability import configure_logging, get_logger
from platform_config import ExecutionMode, PlatformSettings, get_settings
from workflows import build_platform

logger = get_logger(__name__)

DESCRIPTION = """
Reference implementation for **Beyond the Agent**.

The specialized model finds the defect. The platform proves what happened and
governs what happens next.

* Detection is a signal, not a decision.
* Retrieved content is untrusted input, trimmed by entitlement at query time.
* The verdict comes from a versioned policy executing in code.
* Consequential actions require a human approval bound to an exact proposal.
* Exactly one component may mutate a system of record.
* Every transaction seals a verifiable hash-chained audit receipt.

All connectors are **dry-run by default**; nothing here creates a real record.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the platform once, and fail loudly rather than serve half-wired."""
    settings: PlatformSettings = get_settings()
    configure_logging()
    app.state.assembly = build_platform(settings)
    app.state.settings = settings
    logger.info(
        "api_started",
        extra={
            "mode": settings.mode.value,
            "policy_version": app.state.assembly.policy.version,
            "routing_policy_version": app.state.assembly.router.version,
            "dry_run": settings.connector.dry_run,
            "kill_switch": settings.governance.kill_switch_engaged,
        },
    )
    yield
    logger.info("api_stopped", extra={"mode": settings.mode.value})


def create_app(settings: PlatformSettings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    app = FastAPI(
        title="ready-enterprise-ai-platform",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        # Interactive docs are useful in a demo and are an information
        # disclosure surface in production.
        docs_url="/docs" if resolved.mode is not ExecutionMode.PRODUCTION else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved.mode is not ExecutionMode.PRODUCTION else None,
    )

    # Order matters: the outermost middleware runs first on the way in.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1_048_576)
    app.add_middleware(
        CORSMiddleware,
        # Explicit origins only. `*` with credentials is a browser-enforced
        # error and an exfiltration surface without them.
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type", "x-correlation-id", "x-demo-role"],
        max_age=600,
    )

    app.include_router(health.router)
    app.include_router(inspections.router)
    app.include_router(approvals.router)
    app.include_router(governance.router)

    _register_error_handlers(app)
    _instrument(app, resolved)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    """Map typed platform failures onto honest status codes."""

    def _payload(request: Request, error: str, detail: str) -> dict[str, object]:
        return ErrorResponse(
            error=error,
            detail=detail,
            correlation_id=getattr(request.state, "correlation_id", None),
        ).model_dump()

    @app.exception_handler(PolicyDeniedError)
    async def _policy_denied(request: Request, exc: PolicyDeniedError) -> JSONResponse:
        return JSONResponse(
            status_code=403, content=_payload(request, "policy_denied", exc.message)
        )

    @app.exception_handler(ApprovalRequiredError)
    async def _approval_required(request: Request, exc: ApprovalRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=403, content=_payload(request, "approval_required", exc.message)
        )

    @app.exception_handler(KillSwitchEngagedError)
    async def _kill_switch(request: Request, exc: KillSwitchEngagedError) -> JSONResponse:
        return JSONResponse(
            status_code=503, content=_payload(request, "kill_switch_engaged", exc.message)
        )

    @app.exception_handler(UpstreamUnavailableError)
    async def _upstream(request: Request, exc: UpstreamUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content=_payload(request, "upstream_unavailable", exc.message),
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(PlatformError)
    async def _platform(request: Request, exc: PlatformError) -> JSONResponse:
        logger.error("platform_error", extra={"plane": exc.plane, "detail": exc.message})
        return JSONResponse(
            status_code=500, content=_payload(request, "platform_error", exc.message)
        )


def _instrument(app: FastAPI, settings: PlatformSettings) -> None:
    """Attach OpenTelemetry, tolerating its absence rather than failing to start."""
    try:
        from opentelemetry.instrumentation.fastapi import (  # noqa: PLC0415
            FastAPIInstrumentor,
        )
    except ImportError:  # pragma: no cover - optional at runtime
        logger.warning("otel_fastapi_instrumentation_unavailable")
        return

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="livez,readyz",
        tracer_provider=None,
    )
    logger.debug("otel_instrumented", extra={"mode": settings.mode.value})


app = create_app()
