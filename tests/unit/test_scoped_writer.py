"""The sole scoped writer.

This file exists to prove the strongest claim the architecture makes: that a
compromised or merely mistaken reasoning path cannot cause a write. Each test
below removes exactly one control and asserts that the write does not happen.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from approvals import ApprovalService
from connectors import (
    MockEnterpriseConnector,
    ScopedWriter,
    fingerprint_proposal,
    mock_dynamics365,
    mock_erp,
)
from contracts.action import ActionKind, ActionRequest, ActionStatus
from contracts.approval import ApprovalDecision, ApprovalEvidence, ApprovalState
from contracts.errors import (
    ApprovalRequiredError,
    PolicyDeniedError,
    UnauthorizedWriteError,
)
from contracts.policy import PolicyDecision
from policy_engine import PolicyEngine, PolicyInput
from tests.conftest import FIXED_NOW, make_detection

PAYLOAD = {"product_sku": "SKU-88421", "defect_label": "seal_gap", "severity": "major"}


def test_dynamics_365_declares_the_replenishment_action_used_by_the_demo() -> None:
    connector = mock_dynamics365()

    assert ActionKind.CREATE_REPLENISHMENT_ORDER in connector.supported_actions


async def _approved_action(
    approvals: ApprovalService,
    decision: PolicyDecision,
    *,
    target_system: str = "mock-erp",
    kind: ActionKind = ActionKind.CREATE_WORK_ORDER,
    payload: dict[str, str] | None = None,
    idempotency_key: str = "corr-test:decision-1:create_work_order",
) -> tuple[ActionRequest, str]:
    """Produce a fingerprinted, approved action request."""
    body = payload or PAYLOAD
    fingerprint = fingerprint_proposal(
        kind=kind,
        target_system=target_system,
        payload=body,
        policy_decision_id=decision.decision_id,
    )
    record = await approvals.request(
        correlation_id=decision.correlation_id,
        policy_decision_id=decision.decision_id,
        proposal_fingerprint=fingerprint,
        requested_by="synthetic-operator-001",
        required_role=decision.approver_role or "maintenance_lead",
        dual_control_required=decision.dual_control_required,
        proposed_action_summary="raise a maintenance work order",
        evidence=ApprovalEvidence(
            citations=("MS-118",),
            authoritative_values=(("label", "seal_gap"),),
            policy_reason_codes=decision.reason_codes,
            expected_downstream_effect="create_work_order in mock-erp",
            detection_summary="Seal gap at 88% confidence",
        ),
        now=FIXED_NOW,
    )
    await approvals.decide(
        record.approval_id,
        ApprovalDecision(
            approver_principal_id="synthetic-approver-1",
            approver_role=record.request.required_role,
            state=ApprovalState.APPROVED,
            rationale="Evidence and policy reviewed.",
        ),
        now=FIXED_NOW,
    )
    request = ActionRequest(
        correlation_id=decision.correlation_id,
        causation_id=decision.decision_id,
        kind=kind,
        target_system=target_system,
        payload=tuple(sorted(body.items())),
        approval_id=record.approval_id,
        proposal_fingerprint=fingerprint,
        policy_decision_id=decision.decision_id,
        idempotency_key=idempotency_key,
        dry_run=False,
    )
    return request, record.approval_id


@pytest.fixture
def major_decision(policy: PolicyEngine) -> PolicyDecision:
    return policy.evaluate(PolicyInput(detection=make_detection(label="seal_gap", confidence=0.88)))


class TestHappyPath:
    async def test_approved_action_writes_once_and_returns_a_reference(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        connector: MockEnterpriseConnector,
        major_decision: PolicyDecision,
    ) -> None:
        request, _ = await _approved_action(approvals, major_decision)

        receipt = await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

        assert receipt.status is ActionStatus.SUCCEEDED
        assert receipt.external_reference is not None
        assert receipt.external_reference.startswith("WO-")
        assert connector.state.call_count == 1


class TestRefusals:
    async def test_refuses_when_policy_denied_the_transaction(
        self, writer: ScopedWriter, approvals: ApprovalService, policy: PolicyEngine
    ) -> None:
        denied = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="structural_crack", confidence=0.99),
                kill_switch_engaged=True,
            )
        )
        request, _ = await _approved_action(approvals, denied)
        with pytest.raises(PolicyDeniedError):
            await writer.execute(request, policy_decision=denied, now=FIXED_NOW)

    async def test_refuses_an_action_kind_policy_did_not_permit(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        major_decision: PolicyDecision,
    ) -> None:
        """A work-order approval is not a licence to stop the line."""
        request, _ = await _approved_action(
            approvals, major_decision, kind=ActionKind.CREATE_INCIDENT
        )
        with pytest.raises(PolicyDeniedError, match="not in the permitted set"):
            await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

    async def test_refuses_when_the_proposal_changed_after_approval(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        connector: MockEnterpriseConnector,
        major_decision: PolicyDecision,
    ) -> None:
        """The subtlest failure in this pattern, and the reason for the fingerprint."""
        request, _ = await _approved_action(approvals, major_decision)
        tampered = request.model_copy(
            update={"payload": (("product_sku", "SKU-DIFFERENT"), ("severity", "major"))}
        )
        # The fingerprint still matches the *approved* proposal, but re-deriving
        # it from the mutated payload no longer does.
        recomputed = fingerprint_proposal(
            kind=tampered.kind,
            target_system=tampered.target_system,
            payload=tampered.payload_dict(),
            policy_decision_id=major_decision.decision_id,
        )
        assert recomputed != request.proposal_fingerprint

        broken = tampered.model_copy(update={"proposal_fingerprint": recomputed})
        with pytest.raises(ApprovalRequiredError, match="does not match this proposal"):
            await writer.execute(broken, policy_decision=major_decision, now=FIXED_NOW)
        assert connector.state.call_count == 0

    async def test_refuses_an_expired_approval(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        connector: MockEnterpriseConnector,
        major_decision: PolicyDecision,
    ) -> None:
        request, _ = await _approved_action(approvals, major_decision)
        much_later = FIXED_NOW + timedelta(hours=48)
        with pytest.raises(ApprovalRequiredError, match="expired"):
            await writer.execute(request, policy_decision=major_decision, now=much_later)
        assert connector.state.call_count == 0

    async def test_refuses_a_revoked_approval(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        major_decision: PolicyDecision,
    ) -> None:
        request, approval_id = await _approved_action(approvals, major_decision)
        await approvals.revoke(approval_id, now=FIXED_NOW)
        with pytest.raises(ApprovalRequiredError, match="revoked"):
            await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

    async def test_refuses_an_approval_bound_to_a_different_policy_decision(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        policy: PolicyEngine,
        major_decision: PolicyDecision,
    ) -> None:
        request, _ = await _approved_action(approvals, major_decision)
        other = policy.evaluate(
            PolicyInput(detection=make_detection(label="seal_gap", confidence=0.89))
        )
        rebound = request.model_copy(update={"policy_decision_id": other.decision_id})
        with pytest.raises(ApprovalRequiredError, match="different policy decision"):
            await writer.execute(rebound, policy_decision=other, now=FIXED_NOW)

    async def test_refuses_an_action_the_connector_cannot_perform(
        self, approvals: ApprovalService, major_decision: PolicyDecision
    ) -> None:
        from connectors import mock_servicenow  # noqa: PLC0415

        servicenow = mock_servicenow()
        writer = ScopedWriter(connector=servicenow, approvals=approvals, dry_run_default=False)
        request, _ = await _approved_action(
            approvals, major_decision, target_system="mock-servicenow"
        )
        with pytest.raises(UnauthorizedWriteError, match="cannot perform"):
            await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

    async def test_refuses_an_approval_supplied_for_an_ungated_action(
        self, writer: ScopedWriter, policy: PolicyEngine, approvals: ApprovalService
    ) -> None:
        """Supplying an approval where policy required none suggests confusion
        about which decision is being executed, so it fails closed."""
        ungated = policy.evaluate(
            PolicyInput(detection=make_detection(label="surface_scratch", confidence=0.80))
        )
        assert ungated.approval_required is False

        request = ActionRequest(
            correlation_id=ungated.correlation_id,
            causation_id=ungated.decision_id,
            kind=ActionKind.NOTIFY_SUPERVISOR,
            target_system="mock-erp",
            payload=(("note", "cosmetic"),),
            approval_id="apr_unexpected_value",
            proposal_fingerprint=fingerprint_proposal(
                kind=ActionKind.NOTIFY_SUPERVISOR,
                target_system="mock-erp",
                payload={"note": "cosmetic"},
                policy_decision_id=ungated.decision_id,
            ),
            policy_decision_id=ungated.decision_id,
            idempotency_key="corr-x:dec-x:notify_supervisor",
            dry_run=False,
        )
        with pytest.raises(UnauthorizedWriteError, match="policy did not gate"):
            await writer.execute(request, policy_decision=ungated, now=FIXED_NOW)


class TestIdempotency:
    async def test_repeat_of_the_same_decision_never_writes_twice(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        connector: MockEnterpriseConnector,
        major_decision: PolicyDecision,
    ) -> None:
        request, _ = await _approved_action(approvals, major_decision)

        first = await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)
        second = await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

        assert first.status is ActionStatus.SUCCEEDED
        assert second.status is ActionStatus.DUPLICATE_SUPPRESSED
        assert second.external_reference == first.external_reference
        assert connector.state.call_count == 1
        assert len(connector.state.records) == 1

    async def test_a_different_decision_produces_a_different_record(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        connector: MockEnterpriseConnector,
        policy: PolicyEngine,
    ) -> None:
        for index in range(2):
            decision = policy.evaluate(
                PolicyInput(detection=make_detection(label="seal_gap", confidence=0.88))
            )
            request, _ = await _approved_action(
                approvals,
                decision,
                idempotency_key=f"corr-test:{decision.decision_id}:create_work_order-{index}",
            )
            await writer.execute(request, policy_decision=decision, now=FIXED_NOW)
        assert len(connector.state.records) == 2


class TestDryRunAndCompensation:
    async def test_dry_run_is_the_default_and_creates_nothing(
        self, approvals: ApprovalService, major_decision: PolicyDecision
    ) -> None:
        connector = mock_erp()
        writer = ScopedWriter(connector=connector, approvals=approvals, dry_run_default=True)
        request, _ = await _approved_action(approvals, major_decision)

        receipt = await writer.execute(
            request.model_copy(update={"dry_run": False}),
            policy_decision=major_decision,
            now=FIXED_NOW,
        )

        assert receipt.status is ActionStatus.DRY_RUN
        assert connector.state.call_count == 0
        assert connector.state.records == {}

    async def test_transient_failure_is_retried_within_the_budget(
        self, approvals: ApprovalService, major_decision: PolicyDecision
    ) -> None:
        connector = MockEnterpriseConnector(
            system_name="mock-erp",
            reference_prefix="WO",
            supported_actions=frozenset({ActionKind.CREATE_WORK_ORDER}),
            fail_times=1,
        )
        writer = ScopedWriter(connector=connector, approvals=approvals, dry_run_default=False)
        request, _ = await _approved_action(approvals, major_decision)

        receipt = await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

        assert receipt.status is ActionStatus.SUCCEEDED
        assert receipt.attempts == 2

    async def test_permanent_failure_returns_a_failed_receipt_not_an_exception(
        self, approvals: ApprovalService, major_decision: PolicyDecision
    ) -> None:
        """A failed write is still evidence, so it produces a receipt."""
        connector = MockEnterpriseConnector(
            system_name="mock-erp",
            reference_prefix="WO",
            supported_actions=frozenset({ActionKind.CREATE_WORK_ORDER}),
            fail_permanently=True,
        )
        writer = ScopedWriter(connector=connector, approvals=approvals, dry_run_default=False)
        request, _ = await _approved_action(approvals, major_decision)

        receipt = await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

        assert receipt.status is ActionStatus.FAILED
        assert receipt.error_code == "CONNECTOR_UNAVAILABLE"
        assert receipt.attempts >= 1

    async def test_compensation_reverses_an_applied_write(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        connector: MockEnterpriseConnector,
        major_decision: PolicyDecision,
    ) -> None:
        request, _ = await _approved_action(approvals, major_decision)
        receipt = await writer.execute(request, policy_decision=major_decision, now=FIXED_NOW)

        reversal = await writer.compensate(receipt, reason="defect reclassified on re-inspection")

        assert reversal.status is ActionStatus.COMPENSATED
        assert reversal.compensation_of == receipt.receipt_id
        assert connector.state.records[receipt.external_reference or ""].compensated is True

    async def test_only_a_succeeded_write_can_be_compensated(
        self,
        writer: ScopedWriter,
        approvals: ApprovalService,
        major_decision: PolicyDecision,
    ) -> None:
        request, _ = await _approved_action(approvals, major_decision)
        dry = await writer.execute(
            request.model_copy(update={"dry_run": True}),
            policy_decision=major_decision,
            now=FIXED_NOW,
        )
        with pytest.raises(UnauthorizedWriteError):
            await writer.compensate(dry, reason="nothing to reverse")
