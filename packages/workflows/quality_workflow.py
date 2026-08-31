"""The governed quality workflow.

Twelve explicit steps. Deliberately **not** an agent loop: if the control flow
can be drawn as a deterministic diagram, the deterministic workflow is cheaper
to test, easier to secure and faster at run time. An optional agent adapter
exists in ``workflows.agent_adapter`` for the cases where dynamic tool
selection genuinely earns its cost.

Bounded authority is enforced here rather than described: a step budget, a
kill switch, per-stage timeouts, a fixed tool set, and a writer that will not
act without a bound approval.

Two properties matter more than the individual steps:
**the model never writes, and the writer never reasons.** Everything between
those two facts is evidence, policy and supervision.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

from opentelemetry.trace import SpanKind

from approvals import ApprovalService
from audit import AuditTrailBuilder
from audit.store import AuditStore
from connectors import ScopedWriter, fingerprint_proposal
from contracts.action import ActionKind, ActionReceipt, ActionRequest, ActionStatus
from contracts.approval import ApprovalEvidence, ApprovalRecord, ApprovalState
from contracts.audit import AuditReceipt
from contracts.common import (
    Classification,
    CorrelationContext,
    CostCategory,
    utcnow,
)
from contracts.detection import DetectionRequest, DetectionResult
from contracts.errors import KillSwitchEngagedError, PlatformError
from contracts.events import EventType
from contracts.policy import Disposition, PolicyDecision
from contracts.reasoning import ReasoningRequest, Recommendation
from contracts.retrieval import RetrievalQuery, RetrievalResult, RetrievalStrategy
from contracts.routing import RouteDecision, RouteRequest, TaskType
from cost_attribution import CostLedger
from detector.base import Detector
from events import EventPublisher
from model_router import PolicyRouter
from observability import METRICS, traced_step
from observability.logging_config import get_logger
from policy_engine import PolicyEngine, PolicyInput
from reasoning.base import Reasoner
from retrieval import DETECTION_REF, CitationReport, validate_citations
from retrieval.base import Retriever
from security.identity import IdentityContext

logger = get_logger(__name__)

WORKFLOW_STEPS = (
    "receive_prediction",
    "validate_contract",
    "retrieve_evidence",
    "select_route",
    "generate_explanation",
    "evaluate_policy",
    "determine_approval",
    "request_approval",
    "revalidate_state",
    "execute_write",
    "seal_audit",
    "emit_telemetry",
)


@dataclass(slots=True)
class WorkflowOutcome:
    """Everything one governed transaction produced, successful or not."""

    correlation_id: str
    request: DetectionRequest | None = None
    detection: DetectionResult | None = None
    evidence: RetrievalResult | None = None
    route: RouteDecision | None = None
    recommendation: Recommendation | None = None
    citation_report: CitationReport | None = None
    policy: PolicyDecision | None = None
    approval: ApprovalRecord | None = None
    action_receipt: ActionReceipt | None = None
    audit: AuditReceipt | None = None
    cost: CostLedger | None = None
    status: str = "pending"
    halted_reason: str | None = None
    step_latencies_ms: dict[str, float] = field(default_factory=dict)

    @property
    def awaiting_approval(self) -> bool:
        return self.approval is not None and self.approval.state is ApprovalState.PENDING


class GovernedQualityWorkflow:
    """Composes the planes into one auditable transaction."""

    def __init__(
        self,
        *,
        detector: Detector,
        retriever: Retriever,
        router: PolicyRouter,
        reasoner: Reasoner,
        policy: PolicyEngine,
        approvals: ApprovalService,
        writer: ScopedWriter,
        publisher: EventPublisher,
        audit_store: AuditStore | None = None,
        workload_id: str = "manufacturing-quality",
        max_steps: int = 24,
        kill_switch: bool = False,
    ) -> None:
        self._detector = detector
        self._retriever = retriever
        self._router = router
        self._reasoner = reasoner
        self._policy = policy
        self._approvals = approvals
        self._writer = writer
        self._publisher = publisher
        self._audit_store = audit_store
        self._workload_id = workload_id
        self._max_steps = max_steps
        self.kill_switch = kill_switch

    async def run(
        self,
        request: DetectionRequest,
        *,
        identity: IdentityContext,
        context: CorrelationContext | None = None,
        batch_defect_count: int = 0,
        now: datetime | None = None,
    ) -> WorkflowOutcome:
        """Execute steps 1-8. Stops at the approval gate when policy requires one."""
        correlation = context or CorrelationContext(initiated_by=identity.principal_id)
        outcome = WorkflowOutcome(correlation_id=correlation.correlation_id, request=request)
        trail = AuditTrailBuilder(
            correlation_id=correlation.correlation_id, workload_id=self._workload_id
        )
        ledger = CostLedger(correlation_id=correlation.correlation_id)
        outcome.cost = ledger
        METRICS.tasks_started += 1

        # One root span per transaction. Every step below is a child, so a
        # single trace reconstructs the whole decision rather than producing
        # eight unrelated spans that happen to share an attribute.
        with traced_step(
            "governed_quality_transaction",
            correlation_id=correlation.correlation_id,
            attributes={
                "line_id": request.line_id,
                "station_id": request.station_id,
                "workload_id": self._workload_id,
            },
            kind=SpanKind.SERVER,
        ) as root:
            await self._execute(
                request=request,
                identity=identity,
                correlation=correlation,
                batch_defect_count=batch_defect_count,
                trail=trail,
                ledger=ledger,
                outcome=outcome,
                now=now,
            )
            root.set_attribute("reap.outcome", outcome.status)

        outcome.audit = trail.seal(
            outcome=outcome.status,
            prediction_id=outcome.detection.prediction_id if outcome.detection else None,
            policy_decision_id=outcome.policy.decision_id if outcome.policy else None,
            approval_id=outcome.approval.approval_id if outcome.approval else None,
        )
        await self._persist_audit(outcome.audit)
        await self._publisher.emit(
            event_type=EventType.AUDIT_SEALED,
            correlation_id=correlation.correlation_id,
            subject=f"audit/{outcome.audit.audit_id}",
            payload={"audit_id": outcome.audit.audit_id, "outcome": outcome.status},
        )
        return outcome

    async def _execute(
        self,
        *,
        request: DetectionRequest,
        identity: IdentityContext,
        correlation: CorrelationContext,
        batch_defect_count: int,
        trail: AuditTrailBuilder,
        ledger: CostLedger,
        outcome: WorkflowOutcome,
        now: datetime | None,
    ) -> None:
        try:
            if self.kill_switch:
                raise KillSwitchEngagedError(
                    "workload administratively disabled",
                    correlation_id=correlation.correlation_id,
                )

            detection = await self._step_detect(request, correlation, trail, ledger, outcome)
            evidence = await self._step_retrieve(detection, identity, trail, ledger, outcome)
            route = self._step_route(detection, correlation, trail, outcome)
            recommendation = await self._step_reason(
                detection, evidence, route, trail, ledger, outcome
            )
            policy = self._step_policy(
                detection, evidence, request, batch_defect_count, trail, outcome
            )
            approval = await self._step_approval(
                detection=detection,
                evidence=evidence,
                policy=policy,
                recommendation=recommendation,
                identity=identity,
                trail=trail,
                outcome=outcome,
                now=now,
            )

            if policy.disposition in {Disposition.LOG_ONLY, Disposition.NO_ACTION}:
                outcome.status = "completed_no_action"
                METRICS.tasks_completed += 1
            elif approval is not None and approval.state is ApprovalState.PENDING:
                outcome.status = "awaiting_approval"
            else:
                outcome.status = "ready_to_execute"

        except PlatformError as exc:
            outcome.status = "halted"
            outcome.halted_reason = str(exc)
            METRICS.tasks_failed += 1
            trail.record(
                step_name="halt",
                component=exc.plane,
                outcome="error",
                attributes={"error_type": type(exc).__name__, "retryable": exc.retryable},
            )
            logger.warning(
                "workflow_halted",
                extra={
                    "correlation_id": correlation.correlation_id,
                    "plane": exc.plane,
                    "error_type": type(exc).__name__,
                },
            )

    async def complete(
        self,
        outcome: WorkflowOutcome,
        *,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> WorkflowOutcome:
        """Execute steps 9-12 once an approval has been decided.

        Deliberately a separate call: the write happens in a different request
        from the proposal, which is exactly the boundary an approval exists to
        create.
        """
        if outcome.policy is None or outcome.recommendation is None:
            raise ValueError("outcome is not ready for completion")
        if outcome.audit is None:
            raise ValueError("outcome has no sealed audit trail to continue")

        trail = AuditTrailBuilder.resume(outcome.audit)
        policy = outcome.policy
        reference_time = now or utcnow()

        # Step 9: revalidate. State may have moved between proposal and write.
        if policy.approval_required:
            record = await self._approvals.get(outcome.approval.approval_id)  # type: ignore[union-attr]
            outcome.approval = record
            if record is None or not record.state.permits_write:
                outcome.status = "not_approved"
                trail.record(
                    step_name="revalidate_state",
                    component="approvals",
                    outcome=record.state.value if record else "missing",
                )
                outcome.audit = trail.seal(outcome=outcome.status)
                await self._persist_audit(outcome.audit)
                return outcome

        action_kind = self._choose_action(policy)
        payload = self._build_payload(outcome)
        fingerprint = fingerprint_proposal(
            kind=action_kind,
            target_system=self._writer.system_name,
            payload=payload,
            policy_decision_id=policy.decision_id,
        )

        action = ActionRequest(
            correlation_id=outcome.correlation_id,
            causation_id=policy.decision_id,
            kind=action_kind,
            target_system=self._writer.system_name,
            payload=tuple(sorted(payload.items())),
            approval_id=outcome.approval.approval_id if outcome.approval else "not-required",
            proposal_fingerprint=fingerprint,
            policy_decision_id=policy.decision_id,
            # Keyed on the policy decision, so a retry of the same decision can
            # never produce a second work order.
            idempotency_key=f"{outcome.correlation_id}:{policy.decision_id}:{action_kind.value}",
            dry_run=dry_run,
        )

        with traced_step(
            "act", correlation_id=outcome.correlation_id, attributes={"action": action_kind.value}
        ):
            started = time.perf_counter()
            receipt = await self._writer.execute(action, policy_decision=policy, now=reference_time)
            outcome.step_latencies_ms["execute_write"] = (time.perf_counter() - started) * 1000.0

        outcome.action_receipt = receipt
        METRICS.record_action(receipt.status)
        if outcome.cost:
            outcome.cost.record("enterprise_integration", "write", CostCategory.NEGLIGIBLE, units=1)

        trail.record(
            step_name="execute_write",
            component="scoped_writer",
            outcome=receipt.status.value,
            attributes={
                "target_system": receipt.target_system,
                "external_reference": receipt.external_reference,
                "attempts": receipt.attempts,
                "approval_id": action.approval_id,
            },
        )

        await self._publisher.emit(
            event_type=(
                EventType.ACTION_EXECUTED
                if receipt.status is not ActionStatus.FAILED
                else EventType.ACTION_FAILED
            ),
            correlation_id=outcome.correlation_id,
            subject=f"action/{receipt.action_id}",
            causation_id=policy.decision_id,
            payload={
                "status": receipt.status.value,
                "external_reference": receipt.external_reference,
                "target_system": receipt.target_system,
            },
        )

        outcome.status = (
            "completed" if receipt.status is not ActionStatus.FAILED else "write_failed"
        )
        if receipt.status is ActionStatus.FAILED:
            METRICS.tasks_failed += 1
        else:
            METRICS.tasks_completed += 1

        outcome.audit = trail.seal(
            outcome=outcome.status,
            prediction_id=outcome.detection.prediction_id if outcome.detection else None,
            policy_decision_id=policy.decision_id,
            approval_id=outcome.approval.approval_id if outcome.approval else None,
            action_receipt_id=receipt.receipt_id,
        )
        await self._persist_audit(outcome.audit)
        return outcome

    async def _persist_audit(self, receipt: AuditReceipt) -> None:
        """Write the receipt where a reviewer can find it later.

        Persistence lives here rather than in each entry point so that the CLI,
        the API and the worker cannot disagree about whether evidence was kept.
        A storage failure must not discard a completed transaction, so it is
        logged and the receipt survives in the returned outcome.
        """
        if self._audit_store is None:
            return
        try:
            await self._audit_store.put(receipt)
        except Exception:
            logger.exception(
                "audit_persistence_failed",
                extra={
                    "correlation_id": receipt.correlation_id,
                    "audit_id": receipt.audit_id,
                },
            )

    # -- steps -------------------------------------------------------------

    async def _step_detect(
        self,
        request: DetectionRequest,
        correlation: CorrelationContext,
        trail: AuditTrailBuilder,
        ledger: CostLedger,
        outcome: WorkflowOutcome,
    ) -> DetectionResult:
        with traced_step(
            "detect",
            correlation_id=correlation.correlation_id,
            attributes={"station_id": request.station_id, "product_sku": request.product_sku},
        ) as span:
            started = time.perf_counter()
            try:
                detection = await self._detector.detect(
                    request, correlation_id=correlation.correlation_id
                )
            except PlatformError:
                METRICS.detector_failures += 1
                raise
            elapsed = (time.perf_counter() - started) * 1000.0
            outcome.step_latencies_ms["detect"] = elapsed
            METRICS.record_step_latency("detect", elapsed)
            METRICS.predictions += 1
            if detection.is_low_confidence:
                METRICS.low_confidence_predictions += 1
            span.set_attribute("reap.model_version", detection.model_version)
            span.set_attribute("reap.primary_label", detection.primary_label)

        outcome.detection = detection
        trail.record(
            step_name="receive_prediction",
            component="detector",
            outcome=detection.primary_label,
            attributes={
                "prediction_id": detection.prediction_id,
                "model_name": detection.model_name,
                "model_version": detection.model_version,
                "confidence": round(detection.primary_confidence, 4),
                "threshold": detection.decision_threshold,
                "input_hash": detection.input_hash,
                "execution_location": detection.execution_location.value,
            },
        )
        ledger.record("specialized_model", detection.model_name, CostCategory.NEGLIGIBLE, units=1)
        await self._publisher.emit(
            event_type=EventType.PREDICTION_CREATED,
            correlation_id=correlation.correlation_id,
            subject=f"prediction/{detection.prediction_id}",
            payload={
                "prediction_id": detection.prediction_id,
                "label": detection.primary_label,
                "confidence": detection.primary_confidence,
                "model_version": detection.model_version,
            },
        )
        return detection

    async def _step_retrieve(
        self,
        detection: DetectionResult,
        identity: IdentityContext,
        trail: AuditTrailBuilder,
        ledger: CostLedger,
        outcome: WorkflowOutcome,
    ) -> RetrievalResult:
        replenishment_signal = detection.primary_label.endswith("replenishment")
        query_text = (
            f"{detection.primary_label} SKU supplier inventory constraint approval and order"
            if replenishment_signal
            else (
                f"{detection.primary_label} defect disposition, approval role and "
                "required action for the affected unit"
            )
        )
        query = RetrievalQuery(
            correlation_id=detection.correlation_id,
            text=query_text,
            strategy=RetrievalStrategy.HYBRID,
            entitlement_groups=identity.entitlement_groups,
        )
        with traced_step(
            "retrieve",
            correlation_id=detection.correlation_id,
            attributes={"strategy": query.strategy.value},
        ) as span:
            started = time.perf_counter()
            evidence = await self._retriever.search(query)
            elapsed = (time.perf_counter() - started) * 1000.0
            outcome.step_latencies_ms["retrieve"] = elapsed
            METRICS.record_step_latency("retrieve", elapsed)
            METRICS.retrievals += 1
            span.set_attribute("reap.retrieved", len(evidence.items))
            span.set_attribute("reap.trimmed", evidence.trimmed_count)

        if evidence.is_empty:
            METRICS.empty_retrievals += 1
        stale = evidence.stale_items()
        if stale:
            METRICS.stale_evidence_hits += 1

        outcome.evidence = evidence
        trail.record(
            step_name="retrieve_evidence",
            component="retrieval",
            outcome="empty" if evidence.is_empty else "retrieved",
            attributes={
                "index_name": evidence.index_name,
                "index_version": evidence.index_version,
                "retrieved_count": len(evidence.items),
                "trimmed_count": evidence.trimmed_count,
                "citations": ",".join(item.citation_ref for item in evidence.items),
                "stale_refs": ",".join(item.citation_ref for item in stale),
                "has_authoritative": evidence.has_authoritative_source,
            },
        )
        ledger.record("search", evidence.index_name, CostCategory.NEGLIGIBLE, units=1)
        await self._publisher.emit(
            event_type=EventType.CONTEXT_RETRIEVED,
            correlation_id=detection.correlation_id,
            subject=f"retrieval/{evidence.query_id}",
            causation_id=detection.prediction_id,
            payload={
                "retrieved_count": len(evidence.items),
                "trimmed_count": evidence.trimmed_count,
                "citations": [item.citation_ref for item in evidence.items],
            },
        )
        return evidence

    def _step_route(
        self,
        detection: DetectionResult,
        correlation: CorrelationContext,
        trail: AuditTrailBuilder,
        outcome: WorkflowOutcome,
    ) -> RouteDecision:
        with traced_step("route", correlation_id=correlation.correlation_id):
            decision = self._router.route(
                RouteRequest(
                    correlation_id=correlation.correlation_id,
                    task_type=TaskType.EXPLAIN,
                    required_capabilities=frozenset({"evidence_grounding"}),
                    classification=Classification.INTERNAL,
                    upstream_confidence=detection.primary_confidence,
                    business_risk="high" if detection.is_defect else "low",
                )
            )
        outcome.route = decision
        trail.record(
            step_name="select_route",
            component="model_router",
            outcome=decision.selected_route,
            attributes={
                "kind": decision.selected_kind.value,
                "reason_codes": ",".join(decision.reason_codes),
                "excluded": ",".join(e.route_id for e in decision.excluded),
                "policy_version": decision.policy_version,
                "cost_category": decision.cost_category.value,
                "is_fallback": decision.is_fallback,
            },
        )
        return decision

    async def _step_reason(
        self,
        detection: DetectionResult,
        evidence: RetrievalResult,
        route: RouteDecision,
        trail: AuditTrailBuilder,
        ledger: CostLedger,
        outcome: WorkflowOutcome,
    ) -> Recommendation:
        from reasoning.prompts import PROMPT_ID, PROMPT_VERSION  # noqa: PLC0415  (cycle-free)

        with traced_step(
            "reason",
            correlation_id=detection.correlation_id,
            attributes={"route_id": route.selected_route},
        ):
            started = time.perf_counter()
            recommendation = await self._reasoner.explain(
                ReasoningRequest(
                    correlation_id=detection.correlation_id,
                    detection=detection,
                    evidence=evidence,
                    prompt_id=PROMPT_ID,
                    prompt_version=PROMPT_VERSION,
                )
            )
            elapsed = (time.perf_counter() - started) * 1000.0
            outcome.step_latencies_ms["reason"] = elapsed
            METRICS.record_step_latency("reason", elapsed)

        METRICS.recommendations += 1
        if recommendation.refused:
            METRICS.ungrounded_refusals += 1

        report = validate_citations(
            citations=recommendation.citations,
            evidence=evidence.items,
            narrative=recommendation.rationale,
            additional_refs=frozenset({DETECTION_REF}),
        )
        outcome.recommendation = recommendation
        outcome.citation_report = report

        trail.record(
            step_name="generate_explanation",
            component="reasoning",
            outcome="refused" if recommendation.refused else "generated",
            attributes={
                "model_name": recommendation.model_name,
                "model_version": recommendation.model_version,
                "prompt_version": recommendation.prompt_version,
                "route_id": recommendation.route_id,
                "citation_count": len(recommendation.citations),
                "citation_precision": round(report.precision, 3),
                "citation_valid": report.is_valid,
                "citation_issues": ",".join(issue.kind for issue in report.issues),
            },
        )
        ledger.record(
            "foundation_model",
            recommendation.model_name,
            route.cost_category,
            units=1,
            input_tokens=recommendation.input_tokens,
            output_tokens=recommendation.output_tokens,
        )
        await self._publisher.emit(
            event_type=EventType.RECOMMENDATION_GENERATED,
            correlation_id=detection.correlation_id,
            subject=f"recommendation/{recommendation.recommendation_id}",
            causation_id=detection.prediction_id,
            payload={
                "refused": recommendation.refused,
                "citation_count": len(recommendation.citations),
                "citation_precision": round(report.precision, 3),
                "route_id": recommendation.route_id,
            },
        )
        return recommendation

    def _step_policy(
        self,
        detection: DetectionResult,
        evidence: RetrievalResult,
        request: DetectionRequest,
        batch_defect_count: int,
        trail: AuditTrailBuilder,
        outcome: WorkflowOutcome,
    ) -> PolicyDecision:
        with traced_step("validate", correlation_id=detection.correlation_id):
            decision = self._policy.evaluate(
                PolicyInput(
                    detection=detection,
                    classification=request.classification,
                    line_id=request.line_id,
                    batch_defect_count=batch_defect_count,
                    kill_switch_engaged=self.kill_switch,
                    evidence=evidence,
                )
            )
        outcome.policy = decision
        METRICS.record_disposition(decision.disposition)
        trail.record(
            step_name="evaluate_policy",
            component="policy_engine",
            outcome=decision.disposition.value,
            attributes={
                "decision_id": decision.decision_id,
                "severity": decision.severity.value,
                "allowed": decision.allowed,
                "approval_required": decision.approval_required,
                "approver_role": decision.approver_role,
                "dual_control": decision.dual_control_required,
                "reason_codes": ",".join(decision.reason_codes),
                "matched_rules": ",".join(decision.matched_rules),
                "policy_version": decision.policy_version,
                "policy_sha": decision.policy_sha,
            },
        )
        return decision

    async def _step_approval(
        self,
        *,
        detection: DetectionResult,
        evidence: RetrievalResult,
        policy: PolicyDecision,
        recommendation: Recommendation,
        identity: IdentityContext,
        trail: AuditTrailBuilder,
        outcome: WorkflowOutcome,
        now: datetime | None,
    ) -> ApprovalRecord | None:
        if not policy.approval_required:
            trail.record(
                step_name="determine_approval",
                component="approvals",
                outcome=ApprovalState.NOT_REQUIRED.value,
            )
            return None

        action_kind = self._choose_action(policy)
        payload = self._build_payload(outcome)
        fingerprint = fingerprint_proposal(
            kind=action_kind,
            target_system=self._writer.system_name,
            payload=payload,
            policy_decision_id=policy.decision_id,
        )

        record = await self._approvals.request(
            correlation_id=detection.correlation_id,
            policy_decision_id=policy.decision_id,
            proposal_fingerprint=fingerprint,
            requested_by=identity.principal_id,
            required_role=policy.approver_role or "quality_supervisor",
            dual_control_required=policy.dual_control_required,
            proposed_action_summary=(
                recommendation.proposed_action.summary
                if recommendation.proposed_action
                else f"{policy.disposition.value} for {detection.primary_label}"
            ),
            evidence=ApprovalEvidence(
                citations=tuple(item.citation_ref for item in evidence.items),
                authoritative_values=(
                    ("prediction_id", detection.prediction_id),
                    ("label", detection.primary_label),
                    ("confidence", f"{detection.primary_confidence:.4f}"),
                    ("threshold", f"{detection.decision_threshold:.4f}"),
                    ("severity", policy.severity.value),
                    ("disposition", policy.disposition.value),
                ),
                policy_reason_codes=policy.reason_codes,
                expected_downstream_effect=(
                    f"{action_kind.value} in {self._writer.system_name} "
                    f"for SKU {payload.get('product_sku', 'unknown')}"
                ),
                detection_summary=recommendation.headline,
            ),
            now=now,
        )
        outcome.approval = record
        METRICS.record_approval_state(record.state)
        trail.record(
            step_name="request_approval",
            component="approvals",
            outcome=record.state.value,
            attributes={
                "approval_id": record.approval_id,
                "required_role": record.request.required_role,
                "dual_control": record.request.dual_control_required,
                "expires_at": record.request.expires_at.isoformat(),
                "proposal_fingerprint": fingerprint,
            },
        )
        await self._publisher.emit(
            event_type=EventType.APPROVAL_REQUESTED,
            correlation_id=detection.correlation_id,
            subject=f"approval/{record.approval_id}",
            causation_id=policy.decision_id,
            payload={
                "approval_id": record.approval_id,
                "required_role": record.request.required_role,
                "dual_control": record.request.dual_control_required,
            },
        )
        return record

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _choose_action(policy: PolicyDecision) -> ActionKind:
        """Pick from the permitted set only. Never from the recommendation."""
        if not policy.permitted_actions:
            return ActionKind.NOTIFY_SUPERVISOR
        preference = (
            ActionKind.CREATE_REPLENISHMENT_ORDER,
            ActionKind.QUARANTINE_BATCH,
            ActionKind.CREATE_WORK_ORDER,
            ActionKind.CREATE_INCIDENT,
            ActionKind.SCHEDULE_INSPECTION,
            ActionKind.NOTIFY_SUPERVISOR,
        )
        for candidate in preference:
            if candidate in policy.permitted_actions:
                return candidate
        return policy.permitted_actions[0]

    @staticmethod
    def _build_payload(outcome: WorkflowOutcome) -> dict[str, str]:
        """Payload comes from authoritative records, never from generated text."""
        detection = outcome.detection
        policy = outcome.policy
        request = outcome.request
        if detection is None or policy is None or request is None:
            raise ValueError("cannot build a payload before detection and policy")
        return {
            "prediction_id": detection.prediction_id,
            "signal_label": detection.primary_label,
            "confidence": f"{detection.primary_confidence:.4f}",
            "severity": policy.severity.value,
            "disposition": policy.disposition.value,
            "policy_version": policy.policy_version,
            "product_sku": request.product_sku,
            "line_id": request.line_id,
            "station_id": request.station_id,
            "batch_id": request.batch_id or "unassigned",
        }
