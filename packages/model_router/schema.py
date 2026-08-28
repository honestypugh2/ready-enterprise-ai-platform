"""Routing policy schema."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.common import Classification, CostCategory, ExecutionLocation
from contracts.routing import RouteKind, TaskType


class RoutingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RouteDefinition(RoutingModel):
    route_id: str = Field(min_length=1, max_length=64)
    kind: RouteKind
    supports: tuple[TaskType, ...]
    capabilities: tuple[str, ...] = ()
    typical_latency_ms: int = Field(gt=0)
    max_classification: Classification = Classification.INTERNAL
    cost_category: CostCategory = CostCategory.LOW
    execution_location: ExecutionLocation = ExecutionLocation.MOCK
    residency: str | None = None
    deterministic: bool = False
    enabled: bool = True
    evaluation_ref: str | None = None


class RoutingCondition(RoutingModel):
    """Closed vocabulary, same reasoning as the disposition policy."""

    task_type_in: tuple[TaskType, ...] | None = None
    requires_capabilities: tuple[str, ...] | None = None
    classification_at_least: Classification | None = None
    max_latency_ms_below: int | None = Field(default=None, gt=0)
    business_risk_in: tuple[str, ...] | None = None
    upstream_confidence_below: float | None = Field(default=None, ge=0.0, le=1.0)
    residency_equals: str | None = None


class RoutingRule(RoutingModel):
    id: str = Field(pattern=r"^RR\d{3}-[a-z0-9-]+$")
    description: str
    when: RoutingCondition
    prefer: tuple[str, ...] = Field(min_length=1)
    reason_code: str = Field(min_length=3, max_length=64)
    allow_unproven: bool = False


class RoutingFallback(RoutingModel):
    order: tuple[str, ...] = Field(min_length=1)
    reason_code: str


class RoutingPolicy(RoutingModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str
    require_evaluation_evidence: bool = True
    routes: tuple[RouteDefinition, ...]
    rules: tuple[RoutingRule, ...]
    fallback: RoutingFallback
    sha: str = Field(default="", exclude=True)

    def route(self, route_id: str) -> RouteDefinition | None:
        return next((r for r in self.routes if r.route_id == route_id), None)

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        known = {r.route_id for r in self.routes}
        for rule in self.rules:
            unknown = set(rule.prefer) - known
            if unknown:
                raise ValueError(f"rule {rule.id} references unknown routes: {sorted(unknown)}")
        unknown_fallback = set(self.fallback.order) - known
        if unknown_fallback:
            raise ValueError(f"fallback references unknown routes: {sorted(unknown_fallback)}")
        if len({r.route_id for r in self.routes}) != len(self.routes):
            raise ValueError("route ids must be unique")
        # Evaluation is first-match-wins, so file order is part of the contract.
        # Requiring ascending ids keeps "more specific rules first" visible in a
        # diff instead of buried in a reordered block.
        ids = [rule.id for rule in self.rules]
        if ids != sorted(ids):
            raise ValueError("routing rules must be declared in ascending id order")
        return self


def load_routing_policy(path: Path) -> RoutingPolicy:
    if not path.is_file():
        raise FileNotFoundError(f"routing policy not found: {path}")
    raw = path.read_bytes()
    policy = RoutingPolicy.model_validate(yaml.safe_load(raw))
    return policy.model_copy(update={"sha": "sha256:" + hashlib.sha256(raw).hexdigest()})
