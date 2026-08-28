"""Routing contracts.

A route is a policy decision about which component answers a request. It is
recorded with the same rigour as any other policy decision, because "why did
this request reach a frontier model?" is a question an auditor is entitled to
ask six months afterwards.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.common import (
    Classification,
    CostCategory,
    ExecutionLocation,
    PlatformModel,
    new_id,
    utcnow,
)


class TaskType(StrEnum):
    """What the caller needs done. Chosen before any model is considered."""

    CLASSIFY = "classify"
    DETECT = "detect"
    FORECAST = "forecast"
    SCORE = "score"
    CALCULATE = "calculate"
    EXTRACT = "extract"
    EXPLAIN = "explain"
    SUMMARISE = "summarise"
    PLAN = "plan"


class RouteKind(StrEnum):
    """The component family a route resolves to.

    Deterministic code and rules engines are first-class routes. A router that
    can only choose between language models has already conceded the argument.
    """

    DETERMINISTIC_CODE = "deterministic_code"
    RULES_ENGINE = "rules_engine"
    LOCAL_ONNX = "local_onnx"
    AML_ENDPOINT = "aml_endpoint"
    SMALL_LANGUAGE_MODEL = "small_language_model"
    FOUNDRY_MODEL = "foundry_model"
    FOUNDRY_MODEL_ROUTER = "foundry_model_router"
    FRONTIER_MODEL = "frontier_model"
    MOCK = "mock"


class RouteRequest(PlatformModel):
    """Everything the router is permitted to decide on. Nothing else is consulted."""

    request_id: str = Field(default_factory=lambda: new_id("route"))
    correlation_id: str
    task_type: TaskType
    required_capabilities: frozenset[str] = frozenset()

    max_latency_ms: int = Field(gt=0, le=600_000, default=5_000)
    min_throughput_rps: float = Field(ge=0.0, default=0.0)
    classification: Classification = Classification.INTERNAL
    residency: str | None = Field(default=None, max_length=64)
    business_risk: str = Field(default="low", pattern=r"^(low|medium|high|critical)$")
    upstream_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    cost_ceiling: CostCategory = CostCategory.MEDIUM
    fallback_eligible: bool = True
    preferred_location: ExecutionLocation | None = None
    estimated_input_tokens: int = Field(default=0, ge=0)


class RouteCandidate(PlatformModel):
    """A registered route and the properties the policy evaluates it against."""

    route_id: str = Field(min_length=1, max_length=64)
    kind: RouteKind
    supports: frozenset[TaskType]
    capabilities: frozenset[str] = frozenset()
    typical_latency_ms: int = Field(gt=0)
    max_classification: Classification = Classification.INTERNAL
    cost_category: CostCategory = CostCategory.LOW
    execution_location: ExecutionLocation = ExecutionLocation.MOCK
    residency: str | None = None
    deterministic: bool = False
    enabled: bool = True
    # Populated from the evaluation harness. A route with no evaluation evidence
    # is selectable only when the policy explicitly permits unproven routes.
    evaluation_ref: str | None = None


class RouteExclusion(PlatformModel):
    """Why a candidate lost. The rejected list is the interesting half of the log."""

    route_id: str
    reason_code: str = Field(min_length=3, max_length=64)
    detail: str | None = Field(default=None, max_length=300)


class RouteDecision(PlatformModel):
    """The auditable output of routing."""

    decision_id: str = Field(default_factory=lambda: new_id("rd"))
    request_id: str
    correlation_id: str
    selected_route: str
    selected_kind: RouteKind
    reason_codes: tuple[str, ...]
    candidates_considered: tuple[str, ...]
    excluded: tuple[RouteExclusion, ...] = ()
    policy_version: str
    policy_sha: str | None = None
    cost_category: CostCategory
    latency_target_ms: int = Field(gt=0)
    execution_location: ExecutionLocation
    is_fallback: bool = False
    decided_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _selected_not_excluded(self) -> Self:
        if not self.reason_codes:
            raise ValueError("a route decision must carry at least one reason code")
        if self.selected_route in {e.route_id for e in self.excluded}:
            raise ValueError("selected_route cannot also appear in excluded")
        return self
