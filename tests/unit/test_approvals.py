"""Approval lifecycle: expiry, revocation, dual control and separation of duties."""

from __future__ import annotations

from datetime import timedelta

import pytest

from approvals import ApprovalService, InvalidTransitionError, can_transition
from contracts.approval import (
    ApprovalDecision,
    ApprovalEvidence,
    ApprovalState,
)
from contracts.errors import ApprovalRequiredError
from tests.conftest import FIXED_NOW

FINGERPRINT = "sha256:" + "a" * 64


def _evidence() -> ApprovalEvidence:
    return ApprovalEvidence(
        citations=("MS-118",),
        authoritative_values=(("label", "seal_gap"), ("confidence", "0.8810")),
        policy_reason_codes=("SAFETY_RELEVANT_MAJOR_DEFECT",),
        expected_downstream_effect="create_work_order in mock-erp for SKU-88421",
        detection_summary="Seal gap detected at 88% confidence",
    )


async def _request(service: ApprovalService, *, role: str = "maintenance_lead", dual: bool = False):
    return await service.request(
        correlation_id="corr_testtesttest",
        policy_decision_id="pol_testtesttest",
        proposal_fingerprint=FINGERPRINT,
        requested_by="synthetic-operator-001",
        required_role=role,
        dual_control_required=dual,
        proposed_action_summary="raise a maintenance work order",
        evidence=_evidence(),
        now=FIXED_NOW,
    )


def _decision(
    principal: str, *, role: str = "maintenance_lead", state: ApprovalState = ApprovalState.APPROVED
) -> ApprovalDecision:
    return ApprovalDecision(
        approver_principal_id=principal,
        approver_role=role,
        state=state,
        rationale="Evidence, policy result and downstream effect reviewed.",
        decided_at=FIXED_NOW,
    )


class TestApprovalSurface:
    async def test_the_approver_sees_five_things_as_data(self, approvals: ApprovalService) -> None:
        """A natural-language summary on its own is not an approval surface."""
        record = await _request(approvals)
        evidence = record.request.evidence

        assert evidence.citations
        assert evidence.authoritative_values
        assert evidence.policy_reason_codes
        assert evidence.expected_downstream_effect
        assert evidence.detection_summary

    async def test_a_new_request_is_pending_and_carries_an_expiry(
        self, approvals: ApprovalService
    ) -> None:
        record = await _request(approvals)
        assert record.state is ApprovalState.PENDING
        assert record.request.expires_at > record.request.requested_at


class TestSeparationOfDuties:
    async def test_requester_cannot_approve_their_own_proposal(
        self, approvals: ApprovalService
    ) -> None:
        record = await _request(approvals)
        with pytest.raises(ApprovalRequiredError, match="own proposal"):
            await approvals.decide(
                record.approval_id, _decision("synthetic-operator-001"), now=FIXED_NOW
            )

    async def test_wrong_role_cannot_approve(self, approvals: ApprovalService) -> None:
        record = await _request(approvals, role="plant_manager")
        with pytest.raises(ApprovalRequiredError, match="does not satisfy"):
            await approvals.decide(
                record.approval_id,
                _decision("synthetic-approver-1", role="line_operator"),
                now=FIXED_NOW,
            )


class TestDualControl:
    async def test_one_approver_leaves_a_dual_control_approval_pending(
        self, approvals: ApprovalService
    ) -> None:
        record = await _request(approvals, role="plant_manager", dual=True)
        updated = await approvals.decide(
            record.approval_id,
            _decision("synthetic-approver-1", role="plant_manager"),
            now=FIXED_NOW,
        )
        assert updated.state is ApprovalState.PENDING
        assert updated.state.permits_write is False

    async def test_two_distinct_approvers_complete_dual_control(
        self, approvals: ApprovalService
    ) -> None:
        record = await _request(approvals, role="plant_manager", dual=True)
        for principal in ("synthetic-approver-1", "synthetic-approver-2"):
            record = await approvals.decide(
                record.approval_id,
                _decision(principal, role="plant_manager"),
                now=FIXED_NOW,
            )
        assert record.state is ApprovalState.APPROVED
        assert record.state.permits_write is True

    async def test_the_same_person_twice_does_not_satisfy_dual_control(
        self, approvals: ApprovalService
    ) -> None:
        """Otherwise dual control is a formality that one principal can defeat."""
        record = await _request(approvals, role="plant_manager", dual=True)
        for _ in range(2):
            record = await approvals.decide(
                record.approval_id,
                _decision("synthetic-approver-1", role="plant_manager"),
                now=FIXED_NOW,
            )
        assert record.state is ApprovalState.PENDING


class TestTerminalStates:
    async def test_rejection_is_terminal(self, approvals: ApprovalService) -> None:
        record = await _request(approvals)
        rejected = await approvals.decide(
            record.approval_id,
            _decision("synthetic-approver-1", state=ApprovalState.REJECTED),
            now=FIXED_NOW,
        )
        assert rejected.state is ApprovalState.REJECTED
        with pytest.raises(InvalidTransitionError):
            await approvals.decide(
                record.approval_id, _decision("synthetic-approver-2"), now=FIXED_NOW
            )

    async def test_expiry_is_evaluated_at_decision_time(self, approvals: ApprovalService) -> None:
        record = await _request(approvals)
        much_later = FIXED_NOW + timedelta(hours=48)
        expired = await approvals.decide(
            record.approval_id, _decision("synthetic-approver-1"), now=much_later
        )
        assert expired.state is ApprovalState.EXPIRED
        assert expired.state.permits_write is False

    async def test_an_approved_record_can_still_be_revoked(
        self, approvals: ApprovalService
    ) -> None:
        record = await _request(approvals)
        await approvals.decide(record.approval_id, _decision("synthetic-approver-1"), now=FIXED_NOW)
        revoked = await approvals.revoke(record.approval_id, now=FIXED_NOW)
        assert revoked.state is ApprovalState.REVOKED
        assert revoked.state.permits_write is False


class TestStateMachineTable:
    @pytest.mark.parametrize(
        ("current", "target", "allowed"),
        [
            (ApprovalState.PENDING, ApprovalState.APPROVED, True),
            (ApprovalState.PENDING, ApprovalState.PENDING, True),
            (ApprovalState.PENDING, ApprovalState.REJECTED, True),
            (ApprovalState.APPROVED, ApprovalState.REVOKED, True),
            (ApprovalState.APPROVED, ApprovalState.PENDING, False),
            (ApprovalState.REJECTED, ApprovalState.APPROVED, False),
            (ApprovalState.EXPIRED, ApprovalState.APPROVED, False),
            (ApprovalState.REVOKED, ApprovalState.APPROVED, False),
            (ApprovalState.NOT_REQUIRED, ApprovalState.APPROVED, False),
        ],
    )
    def test_transition_table(
        self, current: ApprovalState, target: ApprovalState, allowed: bool
    ) -> None:
        assert can_transition(current, target) is allowed

    def test_only_approved_and_modified_permit_a_write(self) -> None:
        permitting = {s for s in ApprovalState if s.permits_write}
        assert permitting == {ApprovalState.APPROVED, ApprovalState.MODIFIED}


class TestVerifyForWrite:
    async def test_verification_requires_a_matching_fingerprint(
        self, approvals: ApprovalService
    ) -> None:
        record = await _request(approvals)
        await approvals.decide(record.approval_id, _decision("synthetic-approver-1"), now=FIXED_NOW)
        with pytest.raises(ApprovalRequiredError, match="does not match"):
            await approvals.verify_for_write(
                approval_id=record.approval_id,
                proposal_fingerprint="sha256:" + "b" * 64,
                policy_decision_id="pol_testtesttest",
                now=FIXED_NOW,
            )

    async def test_unknown_approval_is_refused(self, approvals: ApprovalService) -> None:
        with pytest.raises(ApprovalRequiredError, match="not found"):
            await approvals.verify_for_write(
                approval_id="apr_does_not_exist",
                proposal_fingerprint=FINGERPRINT,
                policy_decision_id="pol_testtesttest",
                now=FIXED_NOW,
            )
