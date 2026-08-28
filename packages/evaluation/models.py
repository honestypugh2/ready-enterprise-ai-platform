"""Evaluation dataset and system-output models."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.action import ActionKind, ActionStatus
from contracts.detection import DetectionSeverity
from contracts.policy import Disposition


class CaseKind(StrEnum):
    """The five kinds of case a dataset must contain to be worth gating on."""

    GOLDEN = "golden"  # known-correct outcomes
    ADVERSARIAL = "adversarial"  # must fail safely
    EDGE = "edge"  # harvested from real traces
    NEGATIVE = "negative"  # correct behaviour is refusal or escalation
    REGRESSION = "regression"  # a diagnosed production failure, pinned


class EvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedOutcome(EvalModel):
    """What "correct" means for this case, expressed as checkable facts."""

    severity: DetectionSeverity | None = None
    disposition: Disposition | None = None
    approval_required: bool | None = None
    approver_role: str | None = None
    dual_control_required: bool | None = None
    permitted_actions: tuple[ActionKind, ...] | None = None
    action_status: ActionStatus | None = None
    must_refuse: bool = False
    must_cite: tuple[str, ...] = ()
    must_not_cite: tuple[str, ...] = ()
    # Distinct from must_not_cite on purpose. Entitlement is about what came
    # back from the index; citation is about what the answer leaned on. A
    # poisoned document the caller IS entitled to read should be retrieved and
    # must not be cited, and one grader cannot express both.
    must_not_retrieve: tuple[str, ...] = ()
    policy_reason_codes: tuple[str, ...] = ()


class EvalCase(EvalModel):
    case_id: str = Field(min_length=3, max_length=64)
    kind: CaseKind
    description: str = Field(min_length=1, max_length=300)

    frame_seed: str = Field(min_length=1, max_length=128)
    pinned_label: str | None = None
    pinned_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    line_id: str = "DEMO-L1"
    station_id: str = "ST-04"
    product_sku: str = "SKU-DEMO-001"
    classification: str = "internal"
    batch_defect_count: int = Field(default=0, ge=0)
    entitlement_groups: tuple[str, ...] = ("grp-manufacturing-all",)

    expected: ExpectedOutcome

    @model_validator(mode="after")
    def _pin_is_complete(self) -> Self:
        if (self.pinned_label is None) != (self.pinned_confidence is None):
            raise ValueError("pinned_label and pinned_confidence must be set together")
        return self


class EvalDataset(EvalModel):
    dataset_id: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    owner: str
    description: str
    cases: tuple[EvalCase, ...] = Field(min_length=1)

    def of_kind(self, kind: CaseKind) -> tuple[EvalCase, ...]:
        return tuple(case for case in self.cases if case.kind is kind)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique within a dataset")
        return self


class SystemOutput(EvalModel):
    """What the platform produced for one case, flattened for grading."""

    case_id: str
    correlation_id: str

    predicted_label: str
    predicted_confidence: float
    above_threshold: bool

    retrieved_refs: tuple[str, ...] = ()
    trimmed_count: int = 0

    cited_refs: tuple[str, ...] = ()
    citation_precision: float = 0.0
    citation_valid: bool = False
    refused: bool = False
    injection_signals: tuple[str, ...] = ()

    severity: DetectionSeverity | None = None
    disposition: Disposition | None = None
    approval_required: bool | None = None
    approver_role: str | None = None
    dual_control_required: bool = False
    permitted_actions: tuple[ActionKind, ...] = ()
    policy_reason_codes: tuple[str, ...] = ()

    action_kind: ActionKind | None = None
    action_status: ActionStatus | None = None
    wrote_without_approval: bool = False

    status: str = "unknown"
    latency_ms: float = 0.0


def load_dataset(path: Path) -> EvalDataset:
    if not path.is_file():
        raise FileNotFoundError(f"evaluation dataset not found: {path}")
    return EvalDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
