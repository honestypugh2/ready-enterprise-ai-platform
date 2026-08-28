"""Audit receipt builder.

Builds the hash chain incrementally as the workflow executes, so a receipt
exists for a transaction that failed halfway just as surely as for one that
succeeded. A failure with no evidence is the case an auditor asks about first.

Attributes are redacted on the way in, not on the way out: the receipt never
holds a prompt, a passage or a payload value in the first place.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from contracts.audit import GENESIS_HASH, AuditReceipt, AuditStep
from contracts.common import utcnow
from security.redaction import redact_attributes


class AuditTrailBuilder:
    """Accumulates chained steps for one correlation id."""

    def __init__(self, *, correlation_id: str, workload_id: str) -> None:
        self._correlation_id = correlation_id
        self._workload_id = workload_id
        self._steps: list[AuditStep] = []
        self._head = GENESIS_HASH

    @classmethod
    def resume(cls, receipt: AuditReceipt) -> AuditTrailBuilder:
        """Continue an existing chain.

        The proposal and the write happen in different requests, but they are
        one business transaction. Resuming keeps them in a single verifiable
        chain instead of leaving two receipts that a reviewer has to correlate
        by hand.
        """
        builder = cls(correlation_id=receipt.correlation_id, workload_id=receipt.workload_id)
        builder._steps = list(receipt.steps)
        builder._head = receipt.chain_head
        return builder

    @property
    def step_count(self) -> int:
        return len(self._steps)

    def record(
        self,
        *,
        step_name: str,
        component: str,
        outcome: str,
        attributes: Mapping[str, object] | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditStep:
        moment = occurred_at or utcnow()
        safe = redact_attributes(attributes or {})
        ordered = tuple(sorted((k, str(v)) for k, v in safe.items()))
        sequence = len(self._steps)

        entry_hash = AuditStep.compute_hash(
            sequence=sequence,
            step_name=step_name,
            component=component,
            outcome=outcome,
            attributes=ordered,
            occurred_at=moment,
            previous_hash=self._head,
        )
        step = AuditStep(
            sequence=sequence,
            step_name=step_name,
            component=component,
            outcome=outcome,
            attributes=ordered,
            occurred_at=moment,
            previous_hash=self._head,
            entry_hash=entry_hash,
        )
        self._steps.append(step)
        self._head = entry_hash
        return step

    def seal(
        self,
        *,
        outcome: str,
        prediction_id: str | None = None,
        policy_decision_id: str | None = None,
        approval_id: str | None = None,
        action_receipt_id: str | None = None,
        evaluation_ref: str | None = None,
    ) -> AuditReceipt:
        if not self._steps:
            raise ValueError("cannot seal an audit trail with no steps")
        return AuditReceipt(
            correlation_id=self._correlation_id,
            workload_id=self._workload_id,
            steps=tuple(self._steps),
            outcome=outcome,
            prediction_id=prediction_id,
            policy_decision_id=policy_decision_id,
            approval_id=approval_id,
            action_receipt_id=action_receipt_id,
            evaluation_ref=evaluation_ref,
            chain_head=self._head,
        )
