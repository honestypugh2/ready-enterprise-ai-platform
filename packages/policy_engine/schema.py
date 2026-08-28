"""The typed shape of a policy document.

Policy is configuration, but it is configuration with a schema and a test
suite. Loading validates the document; an invalid policy fails at start-up
rather than producing a surprising verdict at request time.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.action import ActionKind
from contracts.detection import DetectionSeverity
from contracts.policy import Disposition


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuleCondition(PolicyModel):
    """Everything a rule is allowed to test. The set is closed on purpose.

    A condition vocabulary that can be extended ad hoc becomes a scripting
    language, and a scripting language in a policy file is no longer reviewable.
    """

    label: str | None = None
    label_in: tuple[str, ...] | None = None
    confidence_at_or_above_threshold: bool | None = None
    confidence_at_least: float | None = Field(default=None, ge=0.0, le=1.0)
    kill_switch_engaged: bool | None = None
    batch_defect_count_at_least: int | None = Field(default=None, ge=0)
    safety_relevant: bool | None = None
    line_in: tuple[str, ...] | None = None


class RuleObligation(PolicyModel):
    id: str
    description: str
    satisfied_by: str


class RuleOutcome(PolicyModel):
    allowed: bool
    severity: DetectionSeverity
    disposition: Disposition
    approval_required: bool
    approver_role: str | None = None
    dual_control_required: bool = False
    permitted_actions: tuple[ActionKind, ...] = ()
    reason_code: str = Field(min_length=3, max_length=64)
    obligations: tuple[RuleObligation, ...] = ()

    @model_validator(mode="after")
    def _denied_permits_nothing(self) -> Self:
        if not self.allowed and self.permitted_actions:
            raise ValueError(f"rule outcome {self.reason_code} denies but permits actions")
        return self


class PolicyRule(PolicyModel):
    id: str = Field(pattern=r"^R\d{3}-[a-z0-9-]+$")
    description: str
    when: RuleCondition = Field(alias="when")
    then: RuleOutcome = Field(alias="then")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class PolicyGuard(PolicyModel):
    """A post-match narrowing rule. Guards may tighten an outcome, never widen it."""

    id: str = Field(pattern=r"^G\d{3}-[a-z0-9-]+$")
    description: str
    dispositions: tuple[Disposition, ...] = ()
    enforce_approval_required: bool = False
    max_classification_for_auto_action: str | None = None
    enforce_approval_when_evidence_stale: bool = False
    reason_code: str | None = None


class PolicyDefaults(PolicyModel):
    severity: DetectionSeverity
    disposition: Disposition
    approval_required: bool
    approver_role: str
    permitted_actions: tuple[ActionKind, ...]
    reason_code: str


class PolicyDocument(PolicyModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str
    defaults: PolicyDefaults
    low_confidence_floor: float = Field(ge=0.0, le=1.0)
    rules: tuple[PolicyRule, ...]
    guards: tuple[PolicyGuard, ...] = ()

    # Not part of the YAML: computed from the file bytes at load time so that
    # every decision can name the exact document that produced it.
    sha: str = Field(default="", exclude=True)

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> Self:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("policy rule ids must be unique")
        # Evaluation is first-match-wins, so file order is part of the contract.
        if ids != sorted(ids):
            raise ValueError("policy rules must be declared in ascending id order")
        return self


def load_policy(path: Path) -> PolicyDocument:
    """Load, validate and hash a policy document."""
    if not path.is_file():
        raise FileNotFoundError(f"policy document not found: {path}")
    raw_bytes = path.read_bytes()
    document = PolicyDocument.model_validate(yaml.safe_load(raw_bytes))
    digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    return document.model_copy(update={"sha": digest})
