"""Reasoner selection."""

from __future__ import annotations

from typing import Any

from platform_config import ExecutionMode, PlatformSettings
from reasoning.base import Reasoner, ReasoningUnavailableError
from reasoning.mock import MockReasoner


def build_reasoner(
    settings: PlatformSettings,
    *,
    credential: Any | None = None,
    route_id: str = "mock-reasoner",
) -> Reasoner:
    config = settings.reasoning

    if config.provider == "mock":
        return MockReasoner()

    if settings.mode is ExecutionMode.LOCAL_MOCK:
        raise ReasoningUnavailableError(
            f"provider={config.provider} requires REAP_MODE=azure_dev or production"
        )
    if not config.endpoint:
        raise ReasoningUnavailableError("REAP_REASONING_ENDPOINT must be set")

    from reasoning.foundry import FoundryReasoner  # noqa: PLC0415  (optional extra)

    # The route decision chooses the deployment; the adapter does not decide
    # for itself which model it is, which is what keeps routing auditable.
    deployment = (
        config.frontier_model_deployment
        if route_id in {"frontier-model", "foundry-model-router"}
        else config.small_model_deployment
    )
    return FoundryReasoner(
        endpoint=config.endpoint,
        deployment=deployment,
        api_version=config.api_version,
        credential=credential,
        route_id=route_id,
        max_output_tokens=config.max_output_tokens,
        temperature=config.temperature,
        timeout_ms=config.timeout_ms,
    )
