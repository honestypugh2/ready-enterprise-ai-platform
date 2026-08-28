"""Every dependency fails, one at a time.

The pattern each test follows: break exactly one thing, then assert the
transaction halts safely, records the reason in the audit trail, and writes
nothing. A platform that keeps answering when its evidence source is down is
not resilient — it is confidently wrong.
"""

from __future__ import annotations

import pytest

from connectors import MockEnterpriseConnector, ScopedWriter
from contracts.action import ActionKind, ActionStatus
from contracts.approval import ApprovalDecision, ApprovalState
from contracts.errors import ApprovalRequiredError, KillSwitchEngagedError
from contracts.retrieval import RetrievalQuery, RetrievalResult, RetrievalStrategy
from detector.base import DetectorUnavailableError
from events import EventPublisher
from reasoning.base import ReasoningUnavailableError, UngroundedOutputError
from retrieval.base import RetrievalUnavailableError
from security.identity import IdentityContext
from workflows import PlatformAssembly
from workflows.quality_workflow import GovernedQualityWorkflow

SCENARIO = "major-defect"

# The same surface mock_erp() exposes. A connector that supports fewer actions
# than the policy permits fails for the wrong reason and hides the one under test.
ERP_ACTIONS = frozenset(
    {
        ActionKind.CREATE_WORK_ORDER,
        ActionKind.QUARANTINE_BATCH,
        ActionKind.SCHEDULE_INSPECTION,
        ActionKind.NOTIFY_SUPERVISOR,
    }
)


def steps_of(outcome: object) -> list[str]:
    return [step.step_name for step in outcome.audit.steps]  # type: ignore[attr-defined]


class FailingRetriever:
    """A retrieval plane that is simply down."""

    index_name = "manufacturing-knowledge"
    index_version = "unavailable"

    async def healthy(self) -> bool:
        return False

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        raise RetrievalUnavailableError("search index is unreachable")


class EmptyRetriever:
    """Reachable, but returns nothing. The quieter and more dangerous failure."""

    index_name = "manufacturing-knowledge"
    index_version = "empty"

    async def healthy(self) -> bool:
        return True

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        return RetrievalResult(
            query_id=query.query_id,
            correlation_id=query.correlation_id,
            strategy=query.strategy,
            items=(),
            latency_ms=1.0,
            index_name=self.index_name,
            index_version=self.index_version,
        )


class PartialRetriever:
    """One shard answered, one did not."""

    index_name = "manufacturing-knowledge"
    index_version = "partial"

    def __init__(self, items: tuple[object, ...]) -> None:
        self._items = items

    async def healthy(self) -> bool:
        return True

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        return RetrievalResult(
            query_id=query.query_id,
            correlation_id=query.correlation_id,
            strategy=RetrievalStrategy.HYBRID,
            items=self._items,  # type: ignore[arg-type]
            latency_ms=1.0,
            index_name=self.index_name,
            index_version=self.index_version,
            partial=True,
            failures=("semantic-shard-2 timed out",),
        )


class FailingReasoner:
    model_name = "unavailable-reasoner"
    model_version = "0"
    route_id = "unavailable"

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def healthy(self) -> bool:
        return False

    async def explain(self, request: object) -> object:
        raise self._error


def rebuild(assembly: PlatformAssembly, **planes: object) -> PlatformAssembly:
    """Recompose the workflow with one plane replaced.

    Uses the same public constructor the composition root uses, so a test can
    break a dependency without reaching into private state.
    """
    assembly.workflow = GovernedQualityWorkflow(
        detector=planes.get("detector", assembly.detector),  # type: ignore[arg-type]
        retriever=planes.get("retriever", assembly.retriever),  # type: ignore[arg-type]
        router=assembly.router,
        reasoner=planes.get("reasoner", assembly.reasoner),  # type: ignore[arg-type]
        policy=assembly.policy,
        approvals=assembly.approvals,
        writer=planes.get("writer", assembly.writer),  # type: ignore[arg-type]
        publisher=EventPublisher(assembly.bus, producer="quality-workflow"),
        audit_store=assembly.audit_store,
        workload_id=assembly.settings.workload_id,
        kill_switch=bool(planes.get("kill_switch", False)),
    )
    return assembly


class TestDetectorFailure:
    async def test_a_detector_outage_halts_before_anything_else_runs(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        assembly.detector.fail_next = True  # type: ignore[attr-defined]
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.status == "halted"
        assert outcome.detection is None
        assert outcome.policy is None
        assert outcome.action_receipt is None

    async def test_the_halt_is_recorded_with_its_plane_and_error_type(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """A failed transaction gets a receipt too. The transaction that did not
        happen is the one an auditor asks about first."""
        assembly.detector.fail_next = True  # type: ignore[attr-defined]
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.audit is not None
        assert outcome.audit.verify_chain()
        assert "halt" in steps_of(outcome)
        halt = next(s for s in outcome.audit.steps if s.step_name == "halt")
        assert halt.component == "detector"
        assert dict(halt.attributes)["error_type"] == "DetectorUnavailableError"

    async def test_a_detector_failure_is_classified_retryable(self) -> None:
        """Retryability is a property of the error, not a guess at the call
        site. A permanent failure retried three times is three outages."""
        assert DetectorUnavailableError("boom").retryable


class TestRetrievalFailure:
    async def test_an_unreachable_index_halts_rather_than_answering_ungrounded(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        rebuild(assembly, retriever=FailingRetriever())
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.status == "halted"
        assert outcome.recommendation is None
        assert outcome.action_receipt is None

    async def test_empty_evidence_does_not_produce_a_confident_answer(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """The failure mode that reads as success. Retrieval worked, returned
        nothing, and a naive pipeline answers anyway."""
        rebuild(assembly, retriever=EmptyRetriever())
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        if outcome.recommendation is not None:
            assert outcome.recommendation.refused
            assert outcome.recommendation.refusal_reason
        assert outcome.action_receipt is None

    async def test_partial_evidence_is_surfaced_not_silently_accepted(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext, settings
    ) -> None:
        from retrieval.local import LocalKnowledgeRetriever  # noqa: PLC0415

        source = LocalKnowledgeRetriever(knowledge_dir=settings.retrieval.knowledge_dir)
        full = await source.search(
            RetrievalQuery(
                correlation_id="corr-partial-source",
                text="seal gap disposition",
                entitlement_groups=identity.entitlement_groups,
                top_k=2,
            )
        )
        rebuild(assembly, retriever=PartialRetriever(full.items))
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.evidence is not None
        assert outcome.evidence.partial
        assert outcome.evidence.failures
        # Degraded retrieval must never quietly become a clean verdict.
        assert outcome.policy is None or outcome.policy.approval_required


class TestReasoningFailure:
    async def test_a_model_outage_halts_the_transaction(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        rebuild(assembly, reasoner=FailingReasoner(ReasoningUnavailableError("endpoint 503")))
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.status == "halted"
        assert outcome.action_receipt is None

    async def test_an_ungrounded_answer_is_treated_as_a_defect_not_a_result(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """A confident paragraph with a decorative footnote is worse than a
        refusal, so it is a non-retryable error rather than a degraded answer."""
        rebuild(assembly, reasoner=FailingReasoner(UngroundedOutputError("no citation resolved")))
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.status == "halted"
        assert not UngroundedOutputError("x").retryable

    async def test_the_evidence_survives_a_reasoning_failure(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """Everything proved before the failure stays in the receipt, so a
        retry starts from evidence rather than from nothing."""
        rebuild(assembly, reasoner=FailingReasoner(ReasoningUnavailableError("endpoint 503")))
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.detection is not None
        assert outcome.evidence is not None
        assert "receive_prediction" in steps_of(outcome)


class TestEnterpriseSystemFailure:
    @staticmethod
    async def _approved(assembly: PlatformAssembly, scenarios, identity: IdentityContext):
        outcome = await assembly.workflow.run(
            scenarios[SCENARIO].to_request(),
            identity=identity,
            batch_defect_count=scenarios[SCENARIO].batch_defect_count,
        )
        assert outcome.approval is not None
        await assembly.approvals.decide(
            outcome.approval.approval_id,
            ApprovalDecision(
                approver_principal_id="synthetic-approver-1",
                approver_role="maintenance_lead",
                state=ApprovalState.APPROVED,
                rationale="Evidence, policy result and downstream effect reviewed.",
            ),
        )
        return outcome

    async def test_a_transient_outage_is_retried_within_budget(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        connector = MockEnterpriseConnector(
            system_name="mock-erp",
            reference_prefix="WO",
            supported_actions=ERP_ACTIONS,
            fail_times=1,
        )
        writer = ScopedWriter(
            connector=connector, approvals=assembly.approvals, dry_run_default=False
        )
        rebuild(assembly, writer=writer)

        outcome = await self._approved(assembly, scenarios, identity)
        outcome = await assembly.workflow.complete(outcome, dry_run=False)

        assert outcome.action_receipt is not None
        assert outcome.action_receipt.status is ActionStatus.SUCCEEDED
        assert outcome.action_receipt.attempts == 2
        assert len(connector.state.records) == 1

    async def test_a_permanent_outage_returns_a_failed_receipt_not_an_exception(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """A downstream outage is an operational fact the caller must see, not
        a stack trace the caller must parse."""
        connector = MockEnterpriseConnector(
            system_name="mock-erp",
            reference_prefix="WO",
            supported_actions=ERP_ACTIONS,
            fail_permanently=True,
        )
        writer = ScopedWriter(
            connector=connector, approvals=assembly.approvals, dry_run_default=False
        )
        rebuild(assembly, writer=writer)

        outcome = await self._approved(assembly, scenarios, identity)
        outcome = await assembly.workflow.complete(outcome, dry_run=False)

        assert outcome.status == "write_failed"
        assert outcome.action_receipt is not None
        assert outcome.action_receipt.status is ActionStatus.FAILED
        assert connector.state.records == {}

    async def test_a_failed_write_still_seals_a_verifiable_audit_chain(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        connector = MockEnterpriseConnector(
            system_name="mock-erp",
            reference_prefix="WO",
            supported_actions=ERP_ACTIONS,
            fail_permanently=True,
        )
        writer = ScopedWriter(
            connector=connector, approvals=assembly.approvals, dry_run_default=False
        )
        rebuild(assembly, writer=writer)

        outcome = await self._approved(assembly, scenarios, identity)
        outcome = await assembly.workflow.complete(outcome, dry_run=False)

        assert outcome.audit is not None
        assert outcome.audit.verify_chain()
        assert "execute_write" in steps_of(outcome)

    async def test_a_write_can_be_compensated_after_the_fact(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """Distributed transactions do not exist across an ERP boundary, so the
        reversal is explicit and gets its own receipt."""
        connector = MockEnterpriseConnector(
            system_name="mock-erp",
            reference_prefix="WO",
            supported_actions=ERP_ACTIONS,
        )
        writer = ScopedWriter(
            connector=connector, approvals=assembly.approvals, dry_run_default=False
        )
        rebuild(assembly, writer=writer)

        outcome = await self._approved(assembly, scenarios, identity)
        outcome = await assembly.workflow.complete(outcome, dry_run=False)
        assert outcome.action_receipt is not None

        reversal = await writer.compensate(
            outcome.action_receipt, reason="operator withdrew the finding"
        )
        assert reversal.status is ActionStatus.COMPENSATED
        assert reversal.compensation_of == outcome.action_receipt.receipt_id
        original = connector.state.records[outcome.action_receipt.external_reference]  # type: ignore[index]
        assert original.compensated


class TestKillSwitch:
    async def test_the_kill_switch_stops_the_workload_before_inference(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """The control an operations team asks for in the first review. It has
        to work without a deployment, and it has to stop the workload before it
        spends anything."""
        rebuild(assembly, kill_switch=True)
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.status == "halted"
        assert outcome.detection is None
        assert outcome.action_receipt is None

    async def test_the_kill_switch_is_still_audited(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        rebuild(assembly, kill_switch=True)
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)

        assert outcome.audit is not None
        assert outcome.audit.verify_chain()
        halt = next(s for s in outcome.audit.steps if s.step_name == "halt")
        assert dict(halt.attributes)["error_type"] == "KillSwitchEngagedError"

    def test_the_kill_switch_error_is_not_retryable(self) -> None:
        """Retrying past an administrative stop defeats the point of it."""
        assert not KillSwitchEngagedError("disabled").retryable


class TestApprovalExpiry:
    async def test_an_expired_approval_does_not_authorise_a_write(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        """Approvals are decisions about a moment. An approval from yesterday
        is not consent for today's state of the line."""
        from datetime import timedelta  # noqa: PLC0415

        from contracts.common import utcnow  # noqa: PLC0415

        outcome = await assembly.workflow.run(
            scenarios[SCENARIO].to_request(),
            identity=identity,
            batch_defect_count=scenarios[SCENARIO].batch_defect_count,
        )
        assert outcome.approval is not None
        await assembly.approvals.decide(
            outcome.approval.approval_id,
            ApprovalDecision(
                approver_principal_id="synthetic-approver-1",
                approver_role="maintenance_lead",
                state=ApprovalState.APPROVED,
                rationale="Evidence, policy result and downstream effect reviewed.",
            ),
        )

        later = utcnow() + timedelta(days=2)
        with pytest.raises(ApprovalRequiredError, match="expired"):
            await assembly.workflow.complete(outcome, dry_run=False, now=later)

    async def test_a_revoked_approval_does_not_authorise_a_write(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        outcome = await assembly.workflow.run(
            scenarios[SCENARIO].to_request(),
            identity=identity,
            batch_defect_count=scenarios[SCENARIO].batch_defect_count,
        )
        assert outcome.approval is not None
        await assembly.approvals.decide(
            outcome.approval.approval_id,
            ApprovalDecision(
                approver_principal_id="synthetic-approver-1",
                approver_role="maintenance_lead",
                state=ApprovalState.APPROVED,
                rationale="Evidence, policy result and downstream effect reviewed.",
            ),
        )
        await assembly.approvals.revoke(outcome.approval.approval_id)

        outcome = await assembly.workflow.complete(outcome, dry_run=False)
        assert outcome.status == "not_approved"
        assert outcome.action_receipt is None


class TestDegradationIsNeverSilent:
    async def test_every_halt_records_a_reason(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        assembly.detector.fail_next = True  # type: ignore[attr-defined]
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)
        assert outcome.halted_reason

    async def test_a_halted_transaction_is_persisted_for_review(
        self, assembly: PlatformAssembly, scenarios, identity: IdentityContext
    ) -> None:
        assembly.detector.fail_next = True  # type: ignore[attr-defined]
        outcome = await assembly.workflow.run(scenarios[SCENARIO].to_request(), identity=identity)
        stored = await assembly.audit_store.get_by_correlation(outcome.correlation_id)
        assert stored is not None
        assert stored.outcome == "halted"
