"""Specialized-model output: the signal, and everything needed to defend it later."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from contracts.common import (
    Classification,
    ExecutionLocation,
    LatencyBudget,
    PlatformModel,
    Provenance,
    new_id,
    utcnow,
)


class DetectionSeverity(StrEnum):
    """Severity of a detected defect class.

    Assigned by the deterministic policy engine from the defect taxonomy, not by
    the detector and never by a language model.
    """

    NONE = "none"
    COSMETIC = "cosmetic"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class DetectionRequest(PlatformModel):
    """One frame submitted for inspection."""

    request_id: str = Field(default_factory=lambda: new_id("det"))
    line_id: str = Field(min_length=1, max_length=64)
    station_id: str = Field(min_length=1, max_length=64)
    product_sku: str = Field(min_length=1, max_length=64)
    batch_id: str | None = Field(default=None, max_length=64)
    # Frames are referenced by hash, never embedded in an event or a trace.
    frame_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    frame_uri: str | None = None
    captured_at: datetime = Field(default_factory=utcnow)
    classification: Classification = Classification.INTERNAL
    budget: LatencyBudget = LatencyBudget(target_ms=150, timeout_ms=2_000)


class Prediction(PlatformModel):
    """A single label emitted by a detector, with the threshold it was judged against."""

    label: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    bounding_box: tuple[float, float, float, float] | None = None

    @property
    def above_threshold(self) -> bool:
        return self.confidence >= self.threshold

    @model_validator(mode="after")
    def _validate_box(self) -> Self:
        if self.bounding_box is not None:
            x0, y0, x1, y1 = self.bounding_box
            if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
                raise ValueError("bounding_box must be normalised x0<x1, y0<y1 within [0,1]")
        return self


class DetectionResult(PlatformModel):
    """The complete, auditable record of one inference.

    Every field here exists because someone eventually asks a question that
    cannot be answered without it: which model version, judged against which
    threshold, on which input, run where, and how long it took.
    """

    prediction_id: str = Field(default_factory=lambda: new_id("pred"))
    request_id: str
    correlation_id: str

    model_name: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    model_sha: str | None = None

    input_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    predictions: tuple[Prediction, ...]
    primary_label: str
    primary_confidence: float = Field(ge=0.0, le=1.0)
    decision_threshold: float = Field(ge=0.0, le=1.0)

    latency_ms: float = Field(ge=0.0)
    execution_location: ExecutionLocation
    detected_at: datetime = Field(default_factory=utcnow)
    provenance: Provenance
    degraded: bool = False
    degraded_reason: str | None = None

    @property
    def is_defect(self) -> bool:
        return (
            self.primary_label != "no_defect" and self.primary_confidence >= self.decision_threshold
        )

    @property
    def is_low_confidence(self) -> bool:
        return self.primary_confidence < self.decision_threshold

    @model_validator(mode="after")
    def _primary_must_be_present(self) -> Self:
        if not self.predictions:
            raise ValueError("a DetectionResult must carry at least one prediction")
        if self.primary_label not in {p.label for p in self.predictions}:
            raise ValueError("primary_label must appear in predictions")
        if self.degraded and not self.degraded_reason:
            raise ValueError("degraded results must carry degraded_reason")
        return self


class DriftSignal(PlatformModel):
    """Observed-versus-registered-baseline comparison for a deployed model."""

    model_name: str
    model_version: str
    metric: str
    baseline_value: float
    observed_value: float
    tolerance: float = Field(gt=0.0)
    window_start: datetime
    window_end: datetime

    @property
    def breached(self) -> bool:
        return abs(self.observed_value - self.baseline_value) > self.tolerance
