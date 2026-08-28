"""Audit receipt: the chain has to fail when it is tampered with.

An audit record that verifies regardless of its contents is decoration. Each
test below mutates exactly one thing and asserts the chain notices.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from audit import AuditTrailBuilder
from contracts.audit import GENESIS_HASH, AuditStep
from tests.conftest import FIXED_NOW


def _trail() -> AuditTrailBuilder:
    builder = AuditTrailBuilder(
        correlation_id="corr_testtesttest", workload_id="manufacturing-quality"
    )
    builder.record(
        step_name="receive_prediction",
        component="detector",
        outcome="seal_gap",
        attributes={"confidence": 0.881, "model_version": "0.3.0-demo"},
        occurred_at=FIXED_NOW,
    )
    builder.record(
        step_name="evaluate_policy",
        component="policy_engine",
        outcome="maintenance_work_order",
        attributes={"policy_version": "2.5.0"},
        occurred_at=FIXED_NOW + timedelta(seconds=1),
    )
    builder.record(
        step_name="execute_write",
        component="scoped_writer",
        outcome="succeeded",
        attributes={"external_reference": "WO-000001"},
        occurred_at=FIXED_NOW + timedelta(seconds=2),
    )
    return builder


class TestChainConstruction:
    def test_a_sealed_receipt_verifies(self) -> None:
        receipt = _trail().seal(outcome="completed")
        assert receipt.verify_chain() is True
        assert len(receipt.steps) == 3

    def test_the_first_step_links_to_genesis(self) -> None:
        receipt = _trail().seal(outcome="completed")
        assert receipt.steps[0].previous_hash == GENESIS_HASH

    def test_each_step_links_to_its_predecessor(self) -> None:
        receipt = _trail().seal(outcome="completed")
        for previous, current in zip(receipt.steps[:-1], receipt.steps[1:], strict=True):
            assert current.previous_hash == previous.entry_hash

    def test_the_head_is_the_last_entry_hash(self) -> None:
        receipt = _trail().seal(outcome="completed")
        assert receipt.chain_head == receipt.steps[-1].entry_hash

    def test_sealing_an_empty_trail_is_refused(self) -> None:
        builder = AuditTrailBuilder(correlation_id="corr_x", workload_id="w")
        with pytest.raises(ValueError, match="no steps"):
            builder.seal(outcome="completed")


class TestTamperDetection:
    def test_editing_a_step_outcome_breaks_the_chain(self) -> None:
        receipt = _trail().seal(outcome="completed")
        tampered = receipt.steps[1].model_copy(update={"outcome": "log_only"})
        assert tampered.verify() is False

    def test_editing_an_attribute_breaks_the_chain(self) -> None:
        receipt = _trail().seal(outcome="completed")
        tampered = receipt.steps[0].model_copy(update={"attributes": (("confidence", "0.100"),)})
        assert tampered.verify() is False

    def test_reordering_steps_breaks_the_chain(self) -> None:
        receipt = _trail().seal(outcome="completed")
        reordered = receipt.model_copy(
            update={"steps": (receipt.steps[1], receipt.steps[0], receipt.steps[2])}
        )
        assert reordered.verify_chain() is False

    def test_dropping_a_step_breaks_the_chain(self) -> None:
        receipt = _trail().seal(outcome="completed")
        truncated = receipt.model_copy(update={"steps": (receipt.steps[0], receipt.steps[2])})
        assert truncated.verify_chain() is False

    def test_a_receipt_that_does_not_verify_cannot_be_constructed(self) -> None:
        """Validation runs on construction, so an invalid receipt never exists."""
        receipt = _trail().seal(outcome="completed")
        forged = AuditStep(
            sequence=0,
            step_name="forged",
            component="attacker",
            outcome="succeeded",
            previous_hash=GENESIS_HASH,
            entry_hash="sha256:" + "f" * 64,
            occurred_at=FIXED_NOW,
        )
        with pytest.raises(ValidationError, match="chain failed verification"):
            receipt.model_copy(update={"steps": (forged,)}).model_validate(
                receipt.model_copy(update={"steps": (forged,)}).model_dump()
            )


class TestRedactionInTheChain:
    def test_sensitive_attribute_values_never_enter_a_receipt(self) -> None:
        """Redaction happens on the way in, so the receipt never holds the value."""
        builder = AuditTrailBuilder(correlation_id="corr_x", workload_id="w")
        builder.record(
            step_name="generate_explanation",
            component="reasoning",
            outcome="generated",
            attributes={
                "prompt": "SYSTEM: you are a quality engineer...",
                "passage": "Confidential paragraph from a retrieved document.",
                "api_key": "sk-live-not-a-real-key-000000",
                "model_version": "gpt-4o-mini",
            },
            occurred_at=FIXED_NOW,
        )
        receipt = builder.seal(outcome="completed")
        attributes = dict(receipt.steps[0].attributes)

        assert attributes["prompt"] == "[redacted]"
        assert attributes["passage"] == "[redacted]"
        assert attributes["api_key"] == "[redacted]"
        # The non-sensitive field survives, because the receipt still has to be useful.
        assert attributes["model_version"] == "gpt-4o-mini"


class TestResume:
    def test_a_trail_can_be_resumed_and_still_verifies(self) -> None:
        """Steps 9-12 happen in a later request than steps 1-8."""
        first = _trail().seal(outcome="awaiting_approval")
        builder = AuditTrailBuilder.resume(first)
        builder.record(
            step_name="seal_audit",
            component="audit",
            outcome="sealed",
            occurred_at=FIXED_NOW + timedelta(minutes=5),
        )
        second = builder.seal(outcome="completed")

        assert second.verify_chain() is True
        assert len(second.steps) == len(first.steps) + 1
        assert second.steps[: len(first.steps)] == first.steps
