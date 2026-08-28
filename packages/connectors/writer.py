"""The sole scoped writer.

This module is the only place in the repository permitted to mutate a system of
record. ``tests/contract/test_sole_writer.py`` asserts that no other module
imports an enterprise connector, and that test failing blocks the build.

``execute`` reads as six refusals followed by one action. None of the refusals
depends on the model behaving well, which is the entire point: if the reasoning
path is compromised, the attacker inherits the reasoning path's permissions, and
those permissions cannot write anything.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from datetime import datetime

from approvals import ApprovalService
from connectors.base import ConnectorError, DuplicateWriteError, EnterpriseConnector
from contracts.action import ActionKind, ActionReceipt, ActionRequest, ActionStatus
from contracts.common import utcnow
from contracts.errors import PolicyDeniedError, UnauthorizedWriteError
from contracts.policy import PolicyDecision


def fingerprint_proposal(
    *,
    kind: ActionKind,
    target_system: str,
    payload: Mapping[str, str],
    policy_decision_id: str,
) -> str:
    """Canonical hash binding an approval to one exact proposal.

    Sorted keys and separator-free JSON make the digest stable across processes,
    which is what lets an approval granted by one instance be verified by
    another.
    """
    canonical = json.dumps(
        {
            "kind": kind.value,
            "target_system": target_system,
            "payload": dict(sorted(payload.items())),
            "policy_decision_id": policy_decision_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ScopedWriter:
    """Executes approved actions, idempotently, under its own narrow authority."""

    def __init__(
        self,
        *,
        connector: EnterpriseConnector,
        approvals: ApprovalService,
        dry_run_default: bool = True,
        max_attempts: int = 3,
    ) -> None:
        self._connector = connector
        self._approvals = approvals
        self._dry_run_default = dry_run_default
        self._max_attempts = max_attempts

    @property
    def system_name(self) -> str:
        return self._connector.system_name

    async def execute(
        self,
        request: ActionRequest,
        *,
        policy_decision: PolicyDecision,
        now: datetime | None = None,
    ) -> ActionReceipt:
        started = time.perf_counter()
        reference_time = now or utcnow()

        # 1. Policy must have permitted this specific action kind.
        if not policy_decision.allowed:
            raise PolicyDeniedError(
                "policy denied this transaction", correlation_id=request.correlation_id
            )
        if request.kind not in policy_decision.permitted_actions:
            raise PolicyDeniedError(
                f"action {request.kind.value} is not in the permitted set",
                correlation_id=request.correlation_id,
            )

        # 2. The approval must bind to this exact proposal and this decision.
        if policy_decision.approval_required:
            await self._approvals.verify_for_write(
                approval_id=request.approval_id,
                proposal_fingerprint=request.proposal_fingerprint,
                policy_decision_id=policy_decision.decision_id,
                now=reference_time,
            )
        elif request.approval_id != "not-required":
            raise UnauthorizedWriteError(
                "an approval was supplied for an action policy did not gate",
                correlation_id=request.correlation_id,
            )

        # 3. The connector must actually support the action.
        if request.kind not in self._connector.supported_actions:
            raise UnauthorizedWriteError(
                f"{self._connector.system_name} cannot perform {request.kind.value}",
                correlation_id=request.correlation_id,
            )

        # 4. Idempotency: a retry after a timeout must never create a second record.
        existing = await self._connector.find_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            return ActionReceipt(
                action_id=request.action_id,
                correlation_id=request.correlation_id,
                status=ActionStatus.DUPLICATE_SUPPRESSED,
                target_system=self._connector.system_name,
                external_reference=existing,
                attempts=0,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                executed_at=reference_time,
            )

        # 5. Dry run is the default. A demonstration that names its mode is more
        #    credible than one that hides it, and nothing here creates a real record.
        if request.dry_run or self._dry_run_default:
            return ActionReceipt(
                action_id=request.action_id,
                correlation_id=request.correlation_id,
                status=ActionStatus.DRY_RUN,
                target_system=self._connector.system_name,
                external_reference=f"DRYRUN-{request.action_id}",
                attempts=0,
                latency_ms=(time.perf_counter() - started) * 1000.0,
                executed_at=reference_time,
            )

        # 6. Only now does anything change.
        return await self._attempt_write(request, started=started, reference_time=reference_time)

    async def compensate(
        self, receipt: ActionReceipt, *, reason: str, now: datetime | None = None
    ) -> ActionReceipt:
        """Reverse an applied write and record the reversal as its own receipt."""
        if receipt.status is not ActionStatus.SUCCEEDED or not receipt.external_reference:
            raise UnauthorizedWriteError("only a succeeded write can be compensated")
        started = time.perf_counter()
        compensation_reference = await self._connector.compensate(
            receipt.external_reference, reason=reason
        )
        return ActionReceipt(
            action_id=receipt.action_id,
            correlation_id=receipt.correlation_id,
            status=ActionStatus.COMPENSATED,
            target_system=self._connector.system_name,
            external_reference=compensation_reference,
            attempts=1,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            compensation_of=receipt.receipt_id,
            executed_at=now or utcnow(),
        )

    async def _attempt_write(
        self, request: ActionRequest, *, started: float, reference_time: datetime
    ) -> ActionReceipt:
        attempts = 0
        last_error: Exception | None = None
        limit = min(request.max_attempts, self._max_attempts)

        while attempts < limit:
            attempts += 1
            try:
                reference = await self._connector.execute(request)
            except DuplicateWriteError:
                existing = await self._connector.find_by_idempotency_key(request.idempotency_key)
                return ActionReceipt(
                    action_id=request.action_id,
                    correlation_id=request.correlation_id,
                    status=ActionStatus.DUPLICATE_SUPPRESSED,
                    target_system=self._connector.system_name,
                    external_reference=existing,
                    attempts=attempts,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    executed_at=reference_time,
                )
            except ConnectorError as exc:
                last_error = exc
                if not exc.retryable:
                    break
                continue
            else:
                return ActionReceipt(
                    action_id=request.action_id,
                    correlation_id=request.correlation_id,
                    status=ActionStatus.SUCCEEDED,
                    target_system=self._connector.system_name,
                    external_reference=reference,
                    attempts=attempts,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                    executed_at=reference_time,
                )

        return ActionReceipt(
            action_id=request.action_id,
            correlation_id=request.correlation_id,
            status=ActionStatus.FAILED,
            target_system=self._connector.system_name,
            attempts=attempts,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error_code="CONNECTOR_UNAVAILABLE",
            error_detail=str(last_error) if last_error else "write did not complete",
            executed_at=reference_time,
        )
