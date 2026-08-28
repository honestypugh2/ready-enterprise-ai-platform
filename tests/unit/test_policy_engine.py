"""Policy engine behaviour, including the boundaries.

Boundary conditions are the point of this file. A policy tested only at its
centre passes while the rule that actually fires in production is wrong by one
comparison operator.
"""

from __future__ import annotations

import pytest

from contracts.action import ActionKind
from contracts.common import Classification
from contracts.detection import DetectionSeverity
from contracts.policy import Disposition
from policy_engine import PolicyEngine, PolicyInput
from tests.conftest import make_detection, make_evidence, make_item


class TestDispositionRules:
    def test_clean_unit_logs_and_requires_no_approval(self, policy: PolicyEngine) -> None:
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="no_defect", confidence=0.97))
        )
        assert decision.allowed
        assert decision.disposition is Disposition.LOG_ONLY
        assert decision.severity is DetectionSeverity.NONE
        assert decision.approval_required is False
        assert decision.permitted_actions == ()

    def test_cosmetic_finding_is_logged_not_actioned(self, policy: PolicyEngine) -> None:
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="surface_scratch", confidence=0.80))
        )
        assert decision.disposition is Disposition.LOG_ONLY
        assert decision.approval_required is False
        assert "COSMETIC_FINDING_LOGGED" in decision.reason_codes

    def test_safety_relevant_major_requires_maintenance_lead(self, policy: PolicyEngine) -> None:
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="seal_gap", confidence=0.88))
        )
        assert decision.disposition is Disposition.MAINTENANCE_WORK_ORDER
        assert decision.severity is DetectionSeverity.MAJOR
        assert decision.approval_required is True
        assert decision.approver_role == "maintenance_lead"
        assert ActionKind.CREATE_WORK_ORDER in decision.permitted_actions

    def test_structural_crack_stops_the_line_under_dual_control(self, policy: PolicyEngine) -> None:
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="structural_crack", confidence=0.94))
        )
        assert decision.disposition is Disposition.STOP_LINE
        assert decision.severity is DetectionSeverity.CRITICAL
        assert decision.dual_control_required is True
        assert decision.approver_role == "plant_manager"
        assert "OB-DUAL-CONTROL" in {o.obligation_id for o in decision.obligations}

    def test_repeat_major_in_batch_escalates_to_line_stop(self, policy: PolicyEngine) -> None:
        """A process fault, not a unit fault. Requires the more specific rule to
        be reachable, which it only is because it is ordered above R040."""
        decision = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="seal_gap", confidence=0.90),
                batch_defect_count=4,
            )
        )
        assert decision.disposition is Disposition.STOP_LINE
        assert "REPEATED_MAJOR_DEFECT_IN_BATCH" in decision.reason_codes
        assert decision.dual_control_required is True


class TestThresholdBoundaries:
    @pytest.mark.parametrize(
        ("confidence", "expect_defect_path"),
        [
            (0.6199, False),  # just below
            (0.6200, True),  # exactly at threshold counts as above
            (0.6201, True),  # just above
        ],
    )
    def test_decision_threshold_is_inclusive(
        self, policy: PolicyEngine, confidence: float, expect_defect_path: bool
    ) -> None:
        decision = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="seal_gap", confidence=confidence, threshold=0.62)
            )
        )
        if expect_defect_path:
            assert decision.disposition is Disposition.MAINTENANCE_WORK_ORDER
        else:
            assert decision.disposition is Disposition.RE_INSPECT
            assert "BELOW_DECISION_THRESHOLD" in decision.reason_codes

    def test_low_confidence_never_raises_a_work_order(self, policy: PolicyEngine) -> None:
        """The model does not stand behind the signal, so neither does the platform."""
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="structural_crack", confidence=0.30))
        )
        assert decision.disposition is Disposition.RE_INSPECT
        assert ActionKind.CREATE_WORK_ORDER not in decision.permitted_actions
        assert decision.approval_required is False

    @pytest.mark.parametrize(
        ("count", "expected"),
        [(2, Disposition.MAINTENANCE_WORK_ORDER), (3, Disposition.STOP_LINE)],
    )
    def test_batch_count_boundary(
        self, policy: PolicyEngine, count: int, expected: Disposition
    ) -> None:
        decision = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="weld_porosity", confidence=0.85),
                batch_defect_count=count,
            )
        )
        assert decision.disposition is expected


class TestGuards:
    def test_restricted_classification_forces_approval(self, policy: PolicyEngine) -> None:
        """A cosmetic finding that would normally auto-log stops for a human."""
        baseline = policy.evaluate(
            PolicyInput(detection=make_detection(label="misalignment", confidence=0.84))
        )
        guarded = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="misalignment", confidence=0.84),
                classification=Classification.RESTRICTED,
            )
        )
        assert baseline.approval_required is True
        assert guarded.approval_required is True
        assert "G002-restricted-classification" in guarded.matched_rules
        assert "RESTRICTED_CLASSIFICATION_REQUIRES_APPROVAL" in guarded.reason_codes

    def test_stale_evidence_forces_approval_on_mutating_disposition(
        self, policy: PolicyEngine
    ) -> None:
        stale = make_evidence(make_item(age_days=400, freshness_slo_days=90))
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="seal_gap", confidence=0.88), evidence=stale)
        )
        assert "G003-stale-evidence" in decision.matched_rules
        assert "STALE_EVIDENCE_REQUIRES_APPROVAL" in decision.reason_codes

    def test_guards_only_narrow_never_widen(self, policy: PolicyEngine) -> None:
        """Whatever a guard does, it cannot remove an approval requirement."""
        with_guard = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="structural_crack", confidence=0.95),
                classification=Classification.RESTRICTED,
                evidence=make_evidence(make_item(age_days=999)),
            )
        )
        assert with_guard.approval_required is True
        assert with_guard.dual_control_required is True


class TestKillSwitch:
    def test_kill_switch_overrides_every_other_rule(self, policy: PolicyEngine) -> None:
        decision = policy.evaluate(
            PolicyInput(
                detection=make_detection(label="structural_crack", confidence=0.99),
                kill_switch_engaged=True,
            )
        )
        assert decision.allowed is False
        assert decision.disposition is Disposition.NO_ACTION
        assert decision.permitted_actions == ()
        assert "KILL_SWITCH_ENGAGED" in decision.reason_codes


class TestDeterminism:
    def test_same_input_and_version_produce_the_same_decision(self, policy: PolicyEngine) -> None:
        """Replayability is what makes the verdict defensible in a review."""
        detection = make_detection(label="seal_gap", confidence=0.88)
        first = policy.evaluate(PolicyInput(detection=detection))
        second = policy.evaluate(PolicyInput(detection=detection))

        assert first.severity == second.severity
        assert first.disposition == second.disposition
        assert first.matched_rules == second.matched_rules
        assert first.reason_codes == second.reason_codes
        assert first.policy_sha == second.policy_sha

    def test_every_decision_names_its_policy_version_and_hash(self, policy: PolicyEngine) -> None:
        decision = policy.evaluate(PolicyInput(detection=make_detection()))
        assert decision.policy_version == policy.version
        assert decision.policy_sha == policy.sha
        assert decision.policy_sha.startswith("sha256:")

    def test_unmatched_input_takes_the_conservative_default(self, policy: PolicyEngine) -> None:
        """A policy whose default is 'allow' is not a control."""
        decision = policy.evaluate(
            PolicyInput(detection=make_detection(label="unknown_defect_class", confidence=0.75))
        )
        assert decision.approval_required is True
        assert decision.disposition is not Disposition.NO_ACTION
        assert ActionKind.CREATE_WORK_ORDER not in decision.permitted_actions


class TestPolicyDocumentIntegrity:
    def test_rule_ids_are_ordered_as_they_are_evaluated(self, policy: PolicyEngine) -> None:
        """First-match-wins makes ordering part of the contract.

        Keeping id order and evaluation order aligned is what stops a more
        specific rule being added below a general one, where it becomes dead
        code that silently never fires.
        """
        rule_ids = [rule.id for rule in policy._doc.rules]
        assert rule_ids == sorted(rule_ids), "rules must be ordered by id"

    def test_denied_outcomes_never_permit_actions(self, policy: PolicyEngine) -> None:
        for rule in policy._doc.rules:
            if not rule.then.allowed:
                assert rule.then.permitted_actions == (), rule.id
