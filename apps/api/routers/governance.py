"""Governance endpoints.

Exposes the artifacts a reviewer asks for: the policy that produced a verdict,
the routing policy that chose a component, a verifiable audit receipt and the
READY AI score. Governance you cannot query is governance you do not have.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from api.dependencies import AssemblyDep, SettingsDep
from contracts.audit import AuditReceipt
from readyai import build_remediation_backlog, evaluate_gate, load_assessment, score_assessment

router = APIRouter(prefix="/v1/governance", tags=["governance"])


@router.get("/policy", summary="The disposition policy currently in force")
async def get_policy(assembly: AssemblyDep) -> dict[str, object]:
    document = assembly.policy.document
    return {
        "version": document.version,
        "sha": assembly.policy.sha,
        "description": document.description,
        "low_confidence_floor": document.low_confidence_floor,
        # Evaluation is first-match-wins, so the order below is the contract,
        # not a presentation choice.
        "rules": [
            {
                "id": rule.id,
                "description": rule.description,
                "disposition": rule.then.disposition.value,
                "severity": rule.then.severity.value,
                "approval_required": rule.then.approval_required,
                "approver_role": rule.then.approver_role,
                "dual_control_required": rule.then.dual_control_required,
                "permitted_actions": [a.value for a in rule.then.permitted_actions],
                "reason_code": rule.then.reason_code,
            }
            for rule in document.rules
        ],
        "guards": [{"id": guard.id, "description": guard.description} for guard in document.guards],
    }


@router.get("/routing-policy", summary="The routing policy currently in force")
async def get_routing_policy(assembly: AssemblyDep) -> dict[str, object]:
    return {
        "version": assembly.router.version,
        "sha": assembly.router.sha,
        "candidates": [
            {
                "route_id": candidate.route_id,
                "kind": candidate.kind.value,
                "deterministic": candidate.deterministic,
                "cost_category": candidate.cost_category.value,
                "typical_latency_ms": candidate.typical_latency_ms,
                "max_classification": candidate.max_classification.value,
                "enabled": candidate.enabled,
                "evaluation_ref": candidate.evaluation_ref,
            }
            for candidate in assembly.router.candidates()
        ],
    }


@router.get("/audit/{correlation_id}", summary="Retrieve and verify an audit receipt")
async def get_audit(correlation_id: str, assembly: AssemblyDep) -> dict[str, object]:
    receipt = await assembly.audit_store.get_by_correlation(correlation_id)
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no audit receipt for that correlation id"
        )
    return _audit_payload(receipt)


@router.get("/readyai", summary="READY AI score for the reference workload")
async def get_readyai(settings: SettingsDep) -> dict[str, object]:
    path = settings.data_dir / "evaluations" / "readyai-sample-assessment.json"
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no assessment document is present"
        )
    return _readyai_payload(path)


def _readyai_payload(path: Path) -> dict[str, object]:
    assessment = load_assessment(path)
    gate = evaluate_gate(assessment)
    return {
        "notice": (
            "READY AI is an original field framework created for the 'Beyond the Agent' "
            "session. It is not an official Microsoft standard."
        ),
        "workload_id": assessment.workload_id,
        "workload_name": assessment.workload_name,
        "risk_tier": assessment.risk_tier,
        "total_score": score_assessment(assessment),
        "band": gate.band.value,
        "gate_passed": gate.passed,
        "blocking_reasons": list(gate.blocking_reasons),
        "lowest_critical": gate.lowest_critical.value if gate.lowest_critical else None,
        "dimensions": [
            {
                "dimension": score.dimension.value,
                "weight": score.weight,
                "level": score.level.value,
                "weighted_score": round(score.weighted_score, 2),
                "evidence": score.evidence,
                "gap": score.gap,
            }
            for score in assessment.scores
        ],
        "remediation_backlog": [
            {"dimension": s.dimension.value, "level": s.level.value, "gap": s.gap}
            for s in build_remediation_backlog(assessment)
        ],
    }


def _audit_payload(receipt: AuditReceipt) -> dict[str, object]:
    return {
        "audit_id": receipt.audit_id,
        "correlation_id": receipt.correlation_id,
        "workload_id": receipt.workload_id,
        "outcome": receipt.outcome,
        "chain_head": receipt.chain_head,
        "chain_verified": receipt.verify_chain(),
        "steps": [
            {
                "sequence": step.sequence,
                "step_name": step.step_name,
                "component": step.component,
                "outcome": step.outcome,
                "occurred_at": step.occurred_at.isoformat(),
                "entry_hash": step.entry_hash,
            }
            for step in receipt.steps
        ],
    }
