"""Approval service.

An approval is bound to a proposal fingerprint. If the proposal changes by a
single byte after a human agreed to it, the binding breaks and the writer
refuses — which closes the subtlest failure in this pattern: a proposal edited
between approval and execution.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from approvals.state_machine import assert_transition
from approvals.store import ApprovalStore, InMemoryApprovalStore
from contracts.approval import (
    ApprovalDecision,
    ApprovalEvidence,
    ApprovalRecord,
    ApprovalRequest,
    ApprovalState,
)
from contracts.common import utcnow
from contracts.errors import ApprovalRequiredError


class ApprovalService:
    """Creates, decides, expires and verifies approvals."""

    def __init__(
        self,
        *,
        store: ApprovalStore | None = None,
        expiry_hours: int = 8,
    ) -> None:
        self._store = store or InMemoryApprovalStore()
        self._expiry_hours = expiry_hours
        self._lock = asyncio.Lock()

    async def request(
        self,
        *,
        correlation_id: str,
        policy_decision_id: str,
        proposal_fingerprint: str,
        requested_by: str,
        required_role: str,
        dual_control_required: bool,
        proposed_action_summary: str,
        evidence: ApprovalEvidence,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        reference = now or utcnow()
        request = ApprovalRequest(
            correlation_id=correlation_id,
            policy_decision_id=policy_decision_id,
            proposal_fingerprint=proposal_fingerprint,
            requested_by=requested_by,
            required_role=required_role,
            dual_control_required=dual_control_required,
            proposed_action_summary=proposed_action_summary,
            evidence=evidence,
            requested_at=reference,
            expires_at=ApprovalRequest.default_expiry(hours=self._expiry_hours, now=reference),
        )
        record = ApprovalRecord(
            approval_id=request.approval_id,
            correlation_id=correlation_id,
            policy_decision_id=policy_decision_id,
            proposal_fingerprint=proposal_fingerprint,
            state=ApprovalState.PENDING,
            request=request,
            updated_at=reference,
        )
        async with self._lock:
            await self._store.put(record)
        return record

    async def decide(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        *,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        """Record one verdict, honouring expiry and dual control."""
        reference = now or utcnow()
        async with self._lock:
            record = await self._require(approval_id)

            if record.is_expired(now=reference) and record.state is ApprovalState.PENDING:
                expired = record.model_copy(
                    update={"state": ApprovalState.EXPIRED, "updated_at": reference}
                )
                await self._store.put(expired)
                return expired

            if decision.approver_principal_id == record.request.requested_by:
                # Separation of duties: the requester cannot approve their own proposal.
                raise ApprovalRequiredError(
                    "requester may not approve their own proposal",
                    correlation_id=record.correlation_id,
                )
            if decision.approver_role != record.request.required_role:
                raise ApprovalRequiredError(
                    f"approver role '{decision.approver_role}' does not satisfy "
                    f"required role '{record.request.required_role}'",
                    correlation_id=record.correlation_id,
                )

            decisions = (*record.decisions, decision)
            target = self._resolve_state(record, decisions, decision)
            assert_transition(record.state, target)

            updated = record.model_copy(
                update={"state": target, "decisions": decisions, "updated_at": reference}
            )
            await self._store.put(updated)
            return updated

    async def revoke(self, approval_id: str, *, now: datetime | None = None) -> ApprovalRecord:
        async with self._lock:
            record = await self._require(approval_id)
            assert_transition(record.state, ApprovalState.REVOKED)
            updated = record.model_copy(
                update={"state": ApprovalState.REVOKED, "updated_at": now or utcnow()}
            )
            await self._store.put(updated)
            return updated

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return await self._store.get(approval_id)

    async def list_pending(self) -> tuple[ApprovalRecord, ...]:
        return await self._store.list_by_state(ApprovalState.PENDING)

    async def verify_for_write(
        self,
        *,
        approval_id: str,
        proposal_fingerprint: str,
        policy_decision_id: str,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        """The check the writer performs. Every failure mode is explicit."""
        record = await self._store.get(approval_id)
        if record is None:
            raise ApprovalRequiredError(f"approval {approval_id} not found")
        if record.proposal_fingerprint != proposal_fingerprint:
            raise ApprovalRequiredError(
                "approval does not match this proposal", correlation_id=record.correlation_id
            )
        if record.policy_decision_id != policy_decision_id:
            raise ApprovalRequiredError(
                "approval is bound to a different policy decision",
                correlation_id=record.correlation_id,
            )
        if record.is_expired(now=now):
            raise ApprovalRequiredError(
                "approval has expired", correlation_id=record.correlation_id
            )
        if not record.state.permits_write:
            raise ApprovalRequiredError(
                f"approval is in state '{record.state.value}'",
                correlation_id=record.correlation_id,
            )
        return record

    # -- internals ---------------------------------------------------------

    async def _require(self, approval_id: str) -> ApprovalRecord:
        record = await self._store.get(approval_id)
        if record is None:
            raise ApprovalRequiredError(f"approval {approval_id} not found")
        return record

    @staticmethod
    def _resolve_state(
        record: ApprovalRecord,
        decisions: tuple[ApprovalDecision, ...],
        latest: ApprovalDecision,
    ) -> ApprovalState:
        if latest.state in {ApprovalState.REJECTED, ApprovalState.REVOKED, ApprovalState.FAILED}:
            return latest.state
        if record.request.dual_control_required:
            # Distinct principals, so one person deciding twice never satisfies
            # dual control. Until the second arrives the approval stays PENDING.
            approvers = {d.approver_principal_id for d in decisions if d.state.permits_write}
            return ApprovalState.APPROVED if len(approvers) >= 2 else ApprovalState.PENDING
        return latest.state
