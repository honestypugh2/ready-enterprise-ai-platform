"""Projection from internal contracts onto the wire schema.

Kept in one place so that "what does the API expose?" has a single answer, and
so the redaction decision for each field is made once rather than in every
router.
"""

from __future__ import annotations

from api.schemas import (
    ActionView,
    ApprovalView,
    AuditStepView,
    AuditView,
    CostView,
    DetectionView,
    EvidenceItemView,
    EvidenceView,
    InspectionResponse,
    PolicyView,
    RecommendationView,
    RouteView,
)
from cost_attribution import RateCard
from workflows import WorkflowOutcome


def detection_view(outcome: WorkflowOutcome) -> DetectionView | None:
    detection = outcome.detection
    if detection is None:
        return None
    return DetectionView(
        prediction_id=detection.prediction_id,
        label=detection.primary_label,
        confidence=detection.primary_confidence,
        threshold=detection.decision_threshold,
        above_threshold=detection.primary_confidence >= detection.decision_threshold,
        model_name=detection.model_name,
        model_version=detection.model_version,
        execution_location=detection.execution_location.value,
        latency_ms=round(detection.latency_ms, 2),
        input_hash=detection.input_hash,
    )


def route_view(outcome: WorkflowOutcome) -> RouteView | None:
    route = outcome.route
    if route is None:
        return None
    return RouteView(
        selected_route=route.selected_route,
        selected_kind=route.selected_kind.value,
        reason_codes=route.reason_codes,
        excluded=tuple(
            {"route_id": e.route_id, "reason_code": e.reason_code, "detail": e.detail}
            for e in route.excluded
        ),
        policy_version=route.policy_version,
        cost_category=route.cost_category.value,
        latency_target_ms=route.latency_target_ms,
        is_fallback=route.is_fallback,
    )


def evidence_view(outcome: WorkflowOutcome) -> EvidenceView | None:
    evidence = outcome.evidence
    if evidence is None:
        return None
    return EvidenceView(
        strategy=evidence.strategy.value,
        index_name=evidence.index_name,
        index_version=evidence.index_version,
        items=tuple(
            EvidenceItemView(
                citation_ref=item.citation_ref,
                source_id=item.source_id,
                source_title=item.source_title,
                source_uri=item.source_uri,
                authority=item.authority,
                classification=item.classification.value,
                version=item.version,
                updated_at=item.updated_at,
                score=round(item.score, 4),
                is_stale=item.is_stale(),
            )
            for item in evidence.items
        ),
        trimmed_count=evidence.trimmed_count,
        partial=evidence.partial,
        failures=evidence.failures,
        latency_ms=round(evidence.latency_ms, 2),
    )


def recommendation_view(outcome: WorkflowOutcome) -> RecommendationView | None:
    recommendation = outcome.recommendation
    if recommendation is None:
        return None
    return RecommendationView(
        headline=recommendation.headline,
        rationale=recommendation.rationale,
        citations=tuple(c.citation_ref for c in recommendation.citations),
        missing_information=recommendation.missing_information,
        refused=recommendation.refused,
        refusal_reason=recommendation.refusal_reason,
        model_name=recommendation.model_name,
        route_id=recommendation.route_id,
        prompt_id=recommendation.prompt_id,
        prompt_version=recommendation.prompt_version,
        citation_precision=(
            round(outcome.citation_report.precision, 4) if outcome.citation_report else None
        ),
        latency_ms=round(recommendation.latency_ms, 2),
    )


def policy_view(outcome: WorkflowOutcome) -> PolicyView | None:
    policy = outcome.policy
    if policy is None:
        return None
    return PolicyView(
        decision_id=policy.decision_id,
        allowed=policy.allowed,
        severity=policy.severity.value,
        disposition=policy.disposition.value,
        approval_required=policy.approval_required,
        approver_role=policy.approver_role,
        dual_control_required=policy.dual_control_required,
        permitted_actions=tuple(a.value for a in policy.permitted_actions),
        reason_codes=policy.reason_codes,
        matched_rules=policy.matched_rules,
        policy_version=policy.policy_version,
        policy_sha=policy.policy_sha,
    )


def approval_view(outcome: WorkflowOutcome) -> ApprovalView | None:
    approval = outcome.approval
    if approval is None:
        return None
    evidence = approval.request.evidence
    return ApprovalView(
        approval_id=approval.approval_id,
        state=approval.state.value,
        required_role=approval.request.required_role,
        dual_control_required=approval.request.dual_control_required,
        requested_at=approval.request.requested_at,
        expires_at=approval.request.expires_at,
        proposal_fingerprint=approval.proposal_fingerprint,
        proposed_action_summary=approval.request.proposed_action_summary,
        evidence={
            "citations": list(evidence.citations),
            "authoritative_values": dict(evidence.authoritative_values),
            "policy_reason_codes": list(evidence.policy_reason_codes),
            "expected_downstream_effect": evidence.expected_downstream_effect,
            "detection_summary": evidence.detection_summary,
        },
        decisions=tuple(
            {
                "approver_principal_id": d.approver_principal_id,
                "approver_role": d.approver_role,
                "state": d.state.value,
                "rationale": d.rationale,
                "decided_at": d.decided_at.isoformat(),
            }
            for d in approval.decisions
        ),
    )


def action_view(outcome: WorkflowOutcome) -> ActionView | None:
    receipt = outcome.action_receipt
    if receipt is None:
        return None
    return ActionView(
        receipt_id=receipt.receipt_id,
        status=receipt.status.value,
        target_system=receipt.target_system,
        external_reference=receipt.external_reference,
        attempts=receipt.attempts,
        error_code=receipt.error_code,
        latency_ms=round(receipt.latency_ms, 2),
    )


def audit_view(outcome: WorkflowOutcome) -> AuditView | None:
    audit = outcome.audit
    if audit is None:
        return None
    return AuditView(
        audit_id=audit.audit_id,
        correlation_id=audit.correlation_id,
        outcome=audit.outcome,
        chain_head=audit.chain_head,
        chain_verified=audit.verify_chain(),
        steps=tuple(
            AuditStepView(
                sequence=step.sequence,
                step_name=step.step_name,
                component=step.component,
                outcome=step.outcome,
                occurred_at=step.occurred_at,
            )
            for step in audit.steps
        ),
    )


def cost_view(outcome: WorkflowOutcome, *, rate_card: RateCard | None = None) -> CostView | None:
    if outcome.cost is None:
        return None
    summary = outcome.cost.summarise(
        rate_card=rate_card, task_completed=outcome.status == "completed"
    )
    return CostView(
        basis=summary.basis.value,
        currency=summary.currency,
        units_by_surface=summary.units_by_surface,
        category_by_surface={k: v.value for k, v in summary.category_by_surface.items()},
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        frontier_calls_avoided=summary.frontier_calls_avoided,
        estimated_total=summary.estimated_total,
        cost_per_completed_task=summary.cost_per_completed_task,
    )


def inspection_response(outcome: WorkflowOutcome, *, mode: str) -> InspectionResponse:
    return InspectionResponse(
        correlation_id=outcome.correlation_id,
        status=outcome.status,
        halted_reason=outcome.halted_reason,
        mode=mode,
        detection=detection_view(outcome),
        route=route_view(outcome),
        evidence=evidence_view(outcome),
        recommendation=recommendation_view(outcome),
        policy=policy_view(outcome),
        approval=approval_view(outcome),
        action=action_view(outcome),
        audit=audit_view(outcome),
        cost=cost_view(outcome),
        step_latencies_ms={k: round(v, 2) for k, v in outcome.step_latencies_ms.items()},
    )
