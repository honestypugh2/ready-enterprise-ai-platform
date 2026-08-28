"""Drives evaluation cases through the real platform.

The point of running the actual workflow rather than a stub is that the number
which gates a release and the number a production dashboard reports come from
the same code. A harness that grades a mock grades the mock.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from contracts.action import ActionKind
from contracts.approval import ApprovalDecision, ApprovalState
from contracts.common import Classification, CorrelationContext, content_hash
from contracts.detection import DetectionRequest
from detector import DeterministicMockDetector
from evaluation.models import EvalCase, SystemOutput
from security.identity import IdentityContext
from workflows.assembly import PlatformAssembly
from workflows.quality_workflow import WorkflowOutcome


def frame_hash_for(case: EvalCase) -> str:
    """Stable frame hash per case, so a rerun grades the same input."""
    return content_hash(case.frame_seed.encode("utf-8"))


class WorkflowEvaluationRunner:
    """Executes one case end to end and flattens the result for grading."""

    def __init__(
        self,
        assembly: PlatformAssembly,
        *,
        auto_approve: bool = True,
    ) -> None:
        self._assembly = assembly
        self._auto_approve = auto_approve

    async def __call__(self, case: EvalCase) -> SystemOutput:
        return await self.run_case(case)

    async def run_case(self, case: EvalCase) -> SystemOutput:
        started = time.perf_counter()
        frame_hash = frame_hash_for(case)

        detector = self._assembly.detector
        if case.pinned_label is not None and isinstance(detector, DeterministicMockDetector):
            # Pinning the detector isolates what is under test: the governance
            # path, not the detector's own accuracy.
            DeterministicMockDetector.pin_scenario(
                frame_hash,
                label=case.pinned_label,
                confidence=case.pinned_confidence or 0.0,
            )

        identity = IdentityContext(
            principal_id=f"eval-operator-{case.case_id}",
            display_name="Evaluation Operator",
            roles=frozenset({"line_operator"}),
            entitlement_groups=frozenset(case.entitlement_groups),
        )
        request = DetectionRequest(
            line_id=case.line_id,
            station_id=case.station_id,
            product_sku=case.product_sku,
            frame_hash=frame_hash,
            classification=Classification(case.classification),
        )

        outcome = await self._assembly.workflow.run(
            request,
            identity=identity,
            context=CorrelationContext(initiated_by=identity.principal_id),
            batch_defect_count=case.batch_defect_count,
        )

        if self._auto_approve and outcome.awaiting_approval and outcome.policy is not None:
            await self._approve(case, outcome)
            outcome = await self._assembly.workflow.complete(outcome, dry_run=True)

        return self._flatten(case, outcome, started=started)

    async def _approve(self, case: EvalCase, outcome: WorkflowOutcome) -> None:
        """Grant the approvals the policy demanded, honouring dual control."""
        policy = outcome.policy
        approval = outcome.approval
        if approval is None or policy is None or policy.approver_role is None:
            return

        approvers = ["primary", "secondary"] if policy.dual_control_required else ["primary"]
        for index, suffix in enumerate(approvers):
            record = await self._assembly.approvals.decide(
                approval.approval_id,
                ApprovalDecision(
                    approver_principal_id=f"eval-approver-{suffix}-{case.case_id}",
                    approver_role=policy.approver_role,
                    state=ApprovalState.APPROVED,
                    rationale=f"Evaluation harness approval {index + 1} for {case.case_id}.",
                ),
            )
            outcome.approval = record

    def _flatten(self, case: EvalCase, outcome: WorkflowOutcome, *, started: float) -> SystemOutput:
        detection = outcome.detection
        evidence = outcome.evidence
        recommendation = outcome.recommendation
        policy = outcome.policy
        receipt = outcome.action_receipt
        report = outcome.citation_report

        retrieved_refs: Sequence[str] = (
            tuple(item.source_id for item in evidence.items) if evidence else ()
        )
        cited_refs: Sequence[str] = (
            tuple(c.source_id for c in recommendation.citations) if recommendation else ()
        )
        injection_signals: Sequence[str] = (
            tuple(evidence.failures) if evidence and evidence.partial else ()
        )

        wrote_without_approval = bool(
            receipt is not None
            and receipt.status.value in {"succeeded", "dry_run"}
            and policy is not None
            and policy.approval_required
            and (outcome.approval is None or not outcome.approval.state.permits_write)
        )

        return SystemOutput(
            case_id=case.case_id,
            correlation_id=outcome.correlation_id,
            predicted_label=detection.primary_label if detection else "unknown",
            predicted_confidence=detection.primary_confidence if detection else 0.0,
            above_threshold=bool(detection and not detection.is_low_confidence),
            retrieved_refs=tuple(retrieved_refs),
            trimmed_count=evidence.trimmed_count if evidence else 0,
            cited_refs=tuple(cited_refs),
            citation_precision=report.precision if report else 0.0,
            citation_valid=bool(report and report.is_valid),
            refused=bool(recommendation and recommendation.refused),
            injection_signals=tuple(injection_signals),
            severity=policy.severity if policy else None,
            disposition=policy.disposition if policy else None,
            approval_required=policy.approval_required if policy else None,
            approver_role=policy.approver_role if policy else None,
            dual_control_required=bool(policy and policy.dual_control_required),
            permitted_actions=policy.permitted_actions if policy else (),
            policy_reason_codes=policy.reason_codes if policy else (),
            action_kind=None if receipt is None else _action_kind(outcome),
            action_status=receipt.status if receipt else None,
            wrote_without_approval=wrote_without_approval,
            status=outcome.status,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


def _action_kind(outcome: WorkflowOutcome) -> ActionKind | None:
    recommendation = outcome.recommendation
    if recommendation is None or recommendation.proposed_action is None:
        return None
    try:
        return ActionKind(recommendation.proposed_action.action_kind)
    except ValueError:
        return None
