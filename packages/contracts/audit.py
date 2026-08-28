"""Audit receipt: the artifact a risk owner reads.

The receipt is a hash chain over the ordered steps of one business transaction.
Tampering with any step invalidates every subsequent link, so the receipt can be
verified without trusting the store it came from.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from contracts.common import CONTRACT_VERSION, PlatformModel, new_id, utcnow

GENESIS_HASH = "sha256:" + "0" * 64


class AuditStep(PlatformModel):
    """One link in the chain. ``attributes`` is redacted before it reaches here."""

    sequence: int = Field(ge=0)
    step_name: str = Field(min_length=1, max_length=64)
    component: str = Field(min_length=1, max_length=64)
    outcome: str = Field(min_length=1, max_length=64)
    attributes: tuple[tuple[str, str], ...] = ()
    occurred_at: datetime = Field(default_factory=utcnow)
    previous_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    entry_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @staticmethod
    def compute_hash(
        *,
        sequence: int,
        step_name: str,
        component: str,
        outcome: str,
        attributes: tuple[tuple[str, str], ...],
        occurred_at: datetime,
        previous_hash: str,
    ) -> str:
        canonical = json.dumps(
            {
                "sequence": sequence,
                "step_name": step_name,
                "component": component,
                "outcome": outcome,
                "attributes": list(attributes),
                "occurred_at": occurred_at.isoformat(),
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify(self) -> bool:
        return self.entry_hash == self.compute_hash(
            sequence=self.sequence,
            step_name=self.step_name,
            component=self.component,
            outcome=self.outcome,
            attributes=self.attributes,
            occurred_at=self.occurred_at,
            previous_hash=self.previous_hash,
        )


class AuditReceipt(PlatformModel):
    """The complete, verifiable record of one governed transaction."""

    audit_id: str = Field(default_factory=lambda: new_id("aud"))
    correlation_id: str
    workload_id: str
    contract_version: str = CONTRACT_VERSION

    steps: tuple[AuditStep, ...]
    outcome: str = Field(min_length=1, max_length=64)
    prediction_id: str | None = None
    policy_decision_id: str | None = None
    approval_id: str | None = None
    action_receipt_id: str | None = None
    evaluation_ref: str | None = None

    chain_head: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=utcnow)

    def verify_chain(self) -> bool:
        """True only when every link hashes correctly and follows its predecessor."""
        previous = GENESIS_HASH
        for index, step in enumerate(self.steps):
            if step.sequence != index or step.previous_hash != previous or not step.verify():
                return False
            previous = step.entry_hash
        return previous == self.chain_head

    @model_validator(mode="after")
    def _chain_must_verify(self) -> Self:
        if not self.steps:
            raise ValueError("an audit receipt must contain at least one step")
        if not self.verify_chain():
            raise ValueError("audit chain failed verification")
        return self
