"""Versioned request and response models for the HTTP surface.

Separate from ``contracts`` on purpose. The internal contract is free to evolve
with the architecture; the wire contract is a promise to a caller. Collapsing
the two means every internal refactor becomes a breaking API change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from contracts.common import Classification


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InspectionRequest(ApiModel):
    """Submit one frame for inspection.

    The frame is referenced by hash, never uploaded inline: the platform stores
    evidence in the evidence store and keeps image bytes out of the API, the
    event bus and the trace.
    """

    line_id: str = Field(min_length=1, max_length=64, examples=["DEMO-L1"])
    station_id: str = Field(min_length=1, max_length=64, examples=["ST-07"])
    product_sku: str = Field(min_length=1, max_length=64, examples=["SKU-88421"])
    batch_id: str | None = Field(default=None, max_length=64, examples=["BATCH-2026-0733"])
    frame_hash: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="SHA-256 of the captured frame, computed at the edge.",
    )
    frame_uri: str | None = Field(default=None, max_length=1_000)
    classification: Classification = Classification.INTERNAL
    batch_defect_count: int = Field(default=0, ge=0, le=10_000)


class ScenarioRequest(ApiModel):
    """Run a pinned demonstration scenario instead of supplying a frame."""

    scenario_id: str = Field(min_length=1, max_length=64, examples=["major-defect"])


class DetectionView(ApiModel):
    prediction_id: str
    label: str
    confidence: float
    threshold: float
    above_threshold: bool
    model_name: str
    model_version: str
    execution_location: str
    latency_ms: float
    input_hash: str


class RouteView(ApiModel):
    selected_route: str
    selected_kind: str
    reason_codes: tuple[str, ...]
    excluded: tuple[dict[str, str | None], ...]
    policy_version: str
    cost_category: str
    latency_target_ms: int
    is_fallback: bool


class EvidenceItemView(ApiModel):
    citation_ref: str
    source_id: str
    source_title: str
    source_uri: str
    authority: str
    classification: str
    version: str
    updated_at: datetime
    score: float
    is_stale: bool


class EvidenceView(ApiModel):
    strategy: str
    index_name: str
    index_version: str
    items: tuple[EvidenceItemView, ...]
    trimmed_count: int
    partial: bool
    failures: tuple[str, ...]
    latency_ms: float


class RecommendationView(ApiModel):
    headline: str
    rationale: str
    citations: tuple[str, ...]
    missing_information: tuple[str, ...]
    refused: bool
    refusal_reason: str | None
    model_name: str
    route_id: str
    prompt_id: str
    prompt_version: str
    citation_precision: float | None
    latency_ms: float


class PolicyView(ApiModel):
    decision_id: str
    allowed: bool
    severity: str
    disposition: str
    approval_required: bool
    approver_role: str | None
    dual_control_required: bool
    permitted_actions: tuple[str, ...]
    reason_codes: tuple[str, ...]
    matched_rules: tuple[str, ...]
    policy_version: str
    policy_sha: str


class ApprovalView(ApiModel):
    approval_id: str
    state: str
    required_role: str
    dual_control_required: bool
    requested_at: datetime
    expires_at: datetime
    proposal_fingerprint: str
    proposed_action_summary: str
    evidence: dict[str, Any]
    decisions: tuple[dict[str, str], ...]


class ActionView(ApiModel):
    receipt_id: str
    status: str
    target_system: str
    external_reference: str | None
    attempts: int
    error_code: str | None
    latency_ms: float


class AuditStepView(ApiModel):
    sequence: int
    step_name: str
    component: str
    outcome: str
    occurred_at: datetime


class AuditView(ApiModel):
    audit_id: str
    correlation_id: str
    outcome: str
    chain_head: str
    chain_verified: bool
    steps: tuple[AuditStepView, ...]


class CostView(ApiModel):
    basis: str
    currency: str
    units_by_surface: dict[str, float]
    category_by_surface: dict[str, str]
    total_input_tokens: int
    total_output_tokens: int
    frontier_calls_avoided: int
    estimated_total: float | None
    cost_per_completed_task: float | None


class InspectionResponse(ApiModel):
    """The full governed transaction, in the order the workflow produced it."""

    correlation_id: str
    status: str
    halted_reason: str | None
    mode: str
    detection: DetectionView | None
    route: RouteView | None
    evidence: EvidenceView | None
    recommendation: RecommendationView | None
    policy: PolicyView | None
    approval: ApprovalView | None
    action: ActionView | None
    audit: AuditView | None
    cost: CostView | None
    step_latencies_ms: dict[str, float]


class ApprovalDecisionRequest(ApiModel):
    """Approve, reject or modify a pending proposal."""

    approver_principal_id: str = Field(min_length=1, max_length=128)
    approver_role: str = Field(min_length=1, max_length=64)
    decision: str = Field(pattern=r"^(approved|rejected|modified)$")
    rationale: str = Field(min_length=1, max_length=1_000)
    modified_payload: dict[str, str] = Field(default_factory=dict)


class HealthResponse(ApiModel):
    status: str
    mode: str
    planes: dict[str, bool]
    policy_version: str
    routing_policy_version: str
    kill_switch_engaged: bool
    dry_run: bool


class ErrorResponse(ApiModel):
    error: str
    detail: str
    correlation_id: str | None = None
