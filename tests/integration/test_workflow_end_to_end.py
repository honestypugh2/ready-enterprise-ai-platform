"""The whole transaction, through the real composition root.

Unit tests prove each control in isolation. This file proves they compose: that
the audit chain covers the same transaction the writer acted on, that the
approval gate actually holds a write rather than merely recording an opinion,
and that every scenario in the demo fixture behaves the way the fixture claims.

The last point matters more than it looks. A demo whose fixtures have drifted
from the policy is a demo that will fail on stage.
"""

from __future__ import annotations

import pytest

from cli.scenarios import DemoScenario
from connectors import ScopedWriter
from contracts.action import ActionStatus
from contracts.approval import ApprovalDecision, ApprovalState
from contracts.events import EventType
from contracts.policy import Disposition
from security.identity import IdentityContext
from workflows import PlatformAssembly
from workflows.quality_workflow import GovernedQualityWorkflow

SCENARIO_IDS = [
    "clean-unit",
    "cosmetic",
    "low-confidence",
    "major-defect",
    "repeat-major",
    "critical-defect",
    "restricted-classification",
]


@pytest.fixture
def executing(assembly: PlatformAssembly) -> PlatformAssembly:
    """The same object graph with the dry-run guard released.

    Local mock mode forces every write to a dry run, which is the promise the
    quickstart makes. To exercise the real write path this fixture composes the
    identical planes with a writer configured the way a deployed environment
    configures it — the same public constructors ``build_platform`` uses, not a
    reach into private state.
    """
    writer = ScopedWriter(
        connector=assembly.connector,
        approvals=assembly.approvals,
        dry_run_default=False,
        max_attempts=assembly.settings.connector.max_attempts,
    )
    from events import EventPublisher  # noqa: PLC0415

    assembly.workflow = GovernedQualityWorkflow(
        detector=assembly.detector,
        retriever=assembly.retriever,
        router=assembly.router,
        reasoner=assembly.reasoner,
        policy=assembly.policy,
        approvals=assembly.approvals,
        writer=writer,
        publisher=EventPublisher(assembly.bus, producer="quality-workflow"),
        workload_id=assembly.settings.workload_id,
        max_steps=assembly.settings.governance.max_workflow_steps,
    )
    assembly.writer = writer
    return assembly


async def approve(
    assembly: PlatformAssembly, approval_id: str, *, role: str, principal: str
) -> None:
    await assembly.approvals.decide(
        approval_id,
        ApprovalDecision(
            approver_principal_id=principal,
            approver_role=role,
            state=ApprovalState.APPROVED,
            rationale="Evidence, policy result and downstream effect reviewed.",
        ),
    )


class TestFixturesMatchPolicy:
    """Every promise in ``demo-scenarios.json`` is checked against the engine."""

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_scenario_produces_the_disposition_it_advertises(
        self,
        scenario_id: str,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios[scenario_id]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.policy is not None
        assert outcome.policy.disposition.value == scenario.expects["disposition"]
        assert outcome.policy.approval_required is scenario.expects["approval_required"]

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    async def test_scenario_matches_the_rule_it_advertises(
        self,
        scenario_id: str,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """Rule ids are the vocabulary the whole talk uses. If a fixture drifts
        onto a different rule, the narration stops being true."""
        scenario = scenarios[scenario_id]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.policy is not None
        assert scenario.expects["policy_rule"] in outcome.policy.matched_rules

    @pytest.mark.parametrize("scenario_id", ["major-defect", "repeat-major", "critical-defect"])
    async def test_gated_scenarios_name_the_role_they_advertise(
        self,
        scenario_id: str,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios[scenario_id]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.policy is not None
        assert outcome.policy.approver_role == scenario.expects["approver_role"]
        assert outcome.policy.dual_control_required is scenario.expects.get(
            "dual_control_required", False
        )


class TestApprovedPathWritesExactlyOnce:
    async def test_local_mock_mode_refuses_a_real_write_even_when_asked(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """The quickstart's central promise. ``dry_run=False`` at the call site
        does not override the configured default, so nothing a caller does in
        local mode can reach a system of record."""
        scenario = scenarios["major-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.approval is not None
        await approve(
            assembly,
            outcome.approval.approval_id,
            role="maintenance_lead",
            principal="synthetic-approver-1",
        )
        outcome = await assembly.workflow.complete(outcome, dry_run=False)

        assert outcome.action_receipt is not None
        assert outcome.action_receipt.status is ActionStatus.DRY_RUN
        assert assembly.connector.state.records == {}

    async def test_a_single_approver_path_completes_and_writes(
        self,
        scenarios: dict[str, DemoScenario],
        executing: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["major-defect"]
        outcome = await executing.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.status == "awaiting_approval"
        assert executing.connector.state.records == {}

        assert outcome.approval is not None
        await approve(
            executing,
            outcome.approval.approval_id,
            role="maintenance_lead",
            principal="synthetic-approver-1",
        )
        outcome = await executing.workflow.complete(outcome, dry_run=False)

        assert outcome.status == "completed"
        assert outcome.action_receipt is not None
        assert outcome.action_receipt.status is ActionStatus.SUCCEEDED
        assert len(executing.connector.state.records) == 1

    async def test_dual_control_holds_the_write_until_the_second_approver(
        self,
        scenarios: dict[str, DemoScenario],
        executing: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["critical-defect"]
        outcome = await executing.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.approval is not None
        approval_id = outcome.approval.approval_id

        await approve(
            executing, approval_id, role="plant_manager", principal="synthetic-approver-1"
        )
        held = await executing.workflow.complete(outcome, dry_run=False)
        assert held.status == "not_approved"
        assert executing.connector.state.records == {}

        await approve(
            executing, approval_id, role="plant_manager", principal="synthetic-approver-2"
        )
        released = await executing.workflow.complete(held, dry_run=False)
        assert released.status == "completed"
        assert len(executing.connector.state.records) == 1

    async def test_replaying_completion_does_not_write_twice(
        self,
        scenarios: dict[str, DemoScenario],
        executing: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """Idempotency is keyed on the policy decision, so a retried completion
        is the same decision and must not produce a second work order."""
        scenario = scenarios["major-defect"]
        outcome = await executing.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.approval is not None
        await approve(
            executing,
            outcome.approval.approval_id,
            role="maintenance_lead",
            principal="synthetic-approver-1",
        )

        first = await executing.workflow.complete(outcome, dry_run=False)
        second = await executing.workflow.complete(first, dry_run=False)

        assert len(executing.connector.state.records) == 1
        assert second.action_receipt is not None
        assert second.action_receipt.status is ActionStatus.DUPLICATE_SUPPRESSED
        assert second.action_receipt.external_reference == (
            first.action_receipt.external_reference  # type: ignore[union-attr]
        )

    async def test_dry_run_produces_a_receipt_but_no_record(
        self,
        scenarios: dict[str, DemoScenario],
        executing: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """The default. A demo that writes for real on a laptop is a demo that
        eventually writes for real somewhere else."""
        scenario = scenarios["major-defect"]
        outcome = await executing.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.approval is not None
        await approve(
            executing,
            outcome.approval.approval_id,
            role="maintenance_lead",
            principal="synthetic-approver-1",
        )
        outcome = await executing.workflow.complete(outcome, dry_run=True)

        assert outcome.action_receipt is not None
        assert outcome.action_receipt.status is ActionStatus.DRY_RUN
        assert executing.connector.state.records == {}


class TestAuditCoversTheWholeTransaction:
    async def test_the_chain_verifies_after_completion(
        self,
        scenarios: dict[str, DemoScenario],
        executing: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["major-defect"]
        outcome = await executing.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.approval is not None
        await approve(
            executing,
            outcome.approval.approval_id,
            role="maintenance_lead",
            principal="synthetic-approver-1",
        )
        outcome = await executing.workflow.complete(outcome, dry_run=False)

        assert outcome.audit is not None
        assert outcome.audit.verify_chain()

    async def test_the_receipt_binds_prediction_policy_approval_and_action(
        self,
        scenarios: dict[str, DemoScenario],
        executing: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """Four identifiers on one receipt is what turns "the AI did it" into a
        reconstructable sequence."""
        scenario = scenarios["major-defect"]
        outcome = await executing.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.approval is not None
        await approve(
            executing,
            outcome.approval.approval_id,
            role="maintenance_lead",
            principal="synthetic-approver-1",
        )
        outcome = await executing.workflow.complete(outcome, dry_run=False)

        receipt = outcome.audit
        assert receipt is not None
        assert receipt.prediction_id == outcome.detection.prediction_id  # type: ignore[union-attr]
        assert receipt.policy_decision_id == outcome.policy.decision_id  # type: ignore[union-attr]
        assert receipt.approval_id == outcome.approval.approval_id
        assert receipt.action_receipt_id == outcome.action_receipt.receipt_id  # type: ignore[union-attr]

    async def test_a_no_action_transaction_is_still_audited(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """The transaction nobody can reconstruct later is the one where nothing
        happened. It gets the same receipt."""
        scenario = scenarios["clean-unit"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.status == "completed_no_action"
        assert outcome.audit is not None
        assert outcome.audit.verify_chain()
        assert len(outcome.audit.steps) >= 4


class TestEventsDescribeTheTransaction:
    async def test_the_expected_events_are_published_in_order(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["major-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        types = assembly.bus.types()  # type: ignore[attr-defined]
        assert types[0] is EventType.PREDICTION_CREATED
        assert EventType.AUDIT_SEALED in types
        assert types.index(EventType.PREDICTION_CREATED) < types.index(EventType.AUDIT_SEALED)
        assert outcome.correlation_id

    async def test_every_event_carries_the_correlation_id(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["major-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        published = assembly.bus.published  # type: ignore[attr-defined]
        assert published
        assert all(e.correlation_id == outcome.correlation_id for e in published)

    async def test_no_action_event_is_emitted_before_approval(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["critical-defect"]
        await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        types = assembly.bus.types()  # type: ignore[attr-defined]
        assert EventType.ACTION_EXECUTED not in types


class TestGroundingAndCitations:
    async def test_the_recommendation_cites_the_evidence_it_used(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["major-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.recommendation is not None
        assert outcome.citation_report is not None
        assert outcome.citation_report.is_valid
        retrieved = {item.citation_ref for item in outcome.evidence.items}  # type: ignore[union-attr]
        cited = {c.citation_ref for c in outcome.recommendation.citations}
        assert cited <= retrieved

    async def test_the_explanation_never_supplies_the_verdict(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """The recommendation is prose plus citations. The disposition comes
        from the policy engine, and the contract has nowhere to put a verdict."""
        scenario = scenarios["critical-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.recommendation is not None
        assert not hasattr(outcome.recommendation, "disposition")
        assert outcome.policy is not None
        assert outcome.policy.disposition is Disposition.STOP_LINE


class TestCostAttribution:
    async def test_cost_is_attributed_per_transaction_not_per_call(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        scenario = scenarios["major-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.cost is not None
        summary = outcome.cost.summarise(task_completed=True)
        assert summary.correlation_id == outcome.correlation_id
        assert summary.entries

    async def test_no_currency_figure_is_invented_without_a_rate_card(
        self,
        scenarios: dict[str, DemoScenario],
        assembly: PlatformAssembly,
        identity: IdentityContext,
    ) -> None:
        """Units are facts. Prices belong to the customer."""
        scenario = scenarios["major-defect"]
        outcome = await assembly.workflow.run(
            scenario.to_request(),
            identity=identity,
            batch_defect_count=scenario.batch_defect_count,
        )
        assert outcome.cost is not None
        summary = outcome.cost.summarise(rate_card=None, task_completed=True)
        assert summary.estimated_total is None
        assert summary.cost_per_completed_task is None
        assert summary.currency == "UNSPECIFIED"
