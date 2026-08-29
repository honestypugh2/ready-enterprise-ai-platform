"""Deterministic policy evaluation.

Same inputs plus same policy version always produce the same decision. That
property is what makes the verdict replayable in an evaluation harness, and it
is the reason this component is code rather than a prompt.

The engine is intentionally boring: ordered first-match-wins, then guards that
can only narrow. Boring is auditable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from contracts.common import Classification
from contracts.detection import DetectionResult
from contracts.policy import Disposition, PolicyDecision, PolicyObligation
from contracts.retrieval import RetrievalResult
from contracts.taxonomy import is_safety_relevant
from policy_engine.schema import PolicyDocument, PolicyRule, RuleCondition, RuleOutcome, load_policy


@dataclass(frozen=True, slots=True)
class PolicyInput:
    """Everything the engine is permitted to consider.

    Notably absent: the model's recommendation. Policy evaluates the signal and
    the evidence, never the narrative written about them.
    """

    detection: DetectionResult
    classification: Classification = Classification.INTERNAL
    line_id: str = "DEMO-L1"
    batch_defect_count: int = 0
    kill_switch_engaged: bool = False
    evidence: RetrievalResult | None = None


class PolicyEngine:
    """Executes a versioned policy document against a `PolicyInput`."""

    def __init__(self, document: PolicyDocument) -> None:
        self._doc = document

    @classmethod
    def from_path(cls, path: Path) -> PolicyEngine:
        return cls(load_policy(path))

    @property
    def version(self) -> str:
        return self._doc.version

    @property
    def sha(self) -> str:
        return self._doc.sha

    @property
    def document(self) -> PolicyDocument:
        """The loaded policy. Frozen, so exposing it cannot mutate the engine."""
        return self._doc

    def evaluate(self, policy_input: PolicyInput) -> PolicyDecision:
        started = time.perf_counter()

        matched = self._first_match(policy_input)
        if matched is None:
            outcome = self._default_outcome()
            matched_rules: tuple[str, ...] = ("DEFAULT",)
        else:
            outcome = matched.then
            matched_rules = (matched.id,)

        reason_codes = [outcome.reason_code]
        approval_required = outcome.approval_required
        approver_role = outcome.approver_role or self._doc.defaults.approver_role
        dual_control = outcome.dual_control_required
        obligations = [
            PolicyObligation(
                obligation_id=item.id,
                description=item.description,
                satisfied_by=item.satisfied_by,
            )
            for item in outcome.obligations
        ]

        applied_guards, approval_required, dual_control, guard_reasons = self._apply_guards(
            outcome=outcome,
            policy_input=policy_input,
            approval_required=approval_required,
            dual_control=dual_control,
        )
        reason_codes.extend(guard_reasons)
        matched_rules = matched_rules + applied_guards

        return PolicyDecision(
            correlation_id=policy_input.detection.correlation_id,
            prediction_id=policy_input.detection.prediction_id,
            allowed=outcome.allowed,
            severity=outcome.severity,
            disposition=outcome.disposition,
            permitted_actions=outcome.permitted_actions,
            approval_required=approval_required,
            approver_role=approver_role if approval_required else None,
            dual_control_required=dual_control,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            matched_rules=matched_rules,
            obligations=tuple(obligations),
            policy_version=self._doc.version,
            policy_sha=self._doc.sha,
            evaluation_ms=(time.perf_counter() - started) * 1000.0,
        )

    # -- internals ---------------------------------------------------------

    def _default_outcome(self) -> RuleOutcome:
        defaults = self._doc.defaults
        return RuleOutcome(
            allowed=True,
            severity=defaults.severity,
            disposition=defaults.disposition,
            approval_required=defaults.approval_required,
            approver_role=defaults.approver_role,
            permitted_actions=defaults.permitted_actions,
            reason_code=defaults.reason_code,
        )

    def _first_match(self, policy_input: PolicyInput) -> PolicyRule | None:
        for rule in self._doc.rules:
            if self._matches(rule.when, policy_input):
                return rule
        return None

    def _matches(self, condition: RuleCondition, policy_input: PolicyInput) -> bool:
        """All specified conditions must hold. Unspecified conditions are ignored.

        Expressed as a flat table so a reviewer can read the whole condition
        vocabulary in one screen, and so adding a condition is a one-line change
        in an obvious place.
        """
        detection = policy_input.detection
        label = detection.primary_label
        above_threshold = detection.primary_confidence >= detection.decision_threshold
        # A detector configured with a permissive threshold would otherwise be
        # deciding when its own output is trustworthy. The floor is policy's.
        below_policy_floor = detection.primary_confidence < self._doc.low_confidence_floor

        checks: tuple[tuple[object | None, bool], ...] = (
            (
                condition.kill_switch_engaged,
                condition.kill_switch_engaged == policy_input.kill_switch_engaged,
            ),
            (condition.label, condition.label == label),
            (condition.label_in, label in (condition.label_in or ())),
            (
                condition.confidence_at_or_above_threshold,
                condition.confidence_at_or_above_threshold == above_threshold,
            ),
            (
                condition.confidence_below_policy_floor,
                condition.confidence_below_policy_floor == below_policy_floor,
            ),
            (
                condition.confidence_at_least,
                detection.primary_confidence >= (condition.confidence_at_least or 0.0),
            ),
            (
                condition.batch_defect_count_at_least,
                policy_input.batch_defect_count >= (condition.batch_defect_count_at_least or 0),
            ),
            (condition.safety_relevant, condition.safety_relevant == is_safety_relevant(label)),
            (condition.line_in, policy_input.line_id in (condition.line_in or ())),
        )
        return all(satisfied for specified, satisfied in checks if specified is not None)

    def _apply_guards(
        self,
        *,
        outcome: RuleOutcome,
        policy_input: PolicyInput,
        approval_required: bool,
        dual_control: bool,
    ) -> tuple[tuple[str, ...], bool, bool, list[str]]:
        applied: list[str] = []
        reasons: list[str] = []

        mutating = {
            Disposition.MAINTENANCE_WORK_ORDER,
            Disposition.QUARANTINE,
            Disposition.STOP_LINE,
        }
        evidence_is_stale = bool(
            policy_input.evidence is not None and policy_input.evidence.stale_items()
        )

        for guard in self._doc.guards:
            gated_dispositions = guard.dispositions or tuple(mutating)
            ceiling = (
                Classification(guard.max_classification_for_auto_action)
                if guard.max_classification_for_auto_action
                else None
            )

            fired = (
                (guard.enforce_approval_required and outcome.disposition in gated_dispositions)
                or (ceiling is not None and policy_input.classification.rank > ceiling.rank)
                or (
                    guard.enforce_approval_when_evidence_stale
                    and evidence_is_stale
                    and outcome.disposition in mutating
                )
            )
            if not fired:
                continue

            # Guards only ever narrow: they can require approval, never remove it.
            approval_required = True
            applied.append(guard.id)
            if guard.reason_code:
                reasons.append(guard.reason_code)

        return tuple(applied), approval_required, dual_control, reasons
