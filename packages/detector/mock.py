"""Deterministic mock detector.

Derives a defect distribution from the SHA-256 of the input frame. The same
frame always produces the same prediction, on any machine, with no weights and
no network — which is what makes the demonstration repeatable on a conference
network and the test suite non-flaky.

It is a fixture, not a model. It carries no accuracy claim of any kind. See
``docs/architecture/model-cards/mock-detector.md``.
"""

from __future__ import annotations

import asyncio
import hashlib

from contracts.common import ExecutionLocation
from contracts.detection import DetectionRequest, Prediction
from contracts.taxonomy import DEFECT_LABELS, NO_DEFECT_LABEL
from detector.base import BaseDetector, DetectorUnavailableError

# Frames whose hash is registered here always produce the same scenario, so the
# demo runbook can promise a specific outcome for a specific fixture.
_PINNED_SCENARIOS: dict[str, tuple[str, float]] = {}


class DeterministicMockDetector(BaseDetector):
    """Hash-seeded detector with pinnable scenarios and injectable failure."""

    def __init__(
        self,
        *,
        model_name: str = "surface-defect-detector",
        model_version: str = "0.3.0-demo",
        decision_threshold: float = 0.62,
        simulated_latency_ms: float = 8.0,
        fail_next: bool = False,
    ) -> None:
        super().__init__(decision_threshold=decision_threshold)
        self.model_name = model_name
        self.model_version = model_version
        self.execution_location = ExecutionLocation.MOCK
        self._simulated_latency_ms = simulated_latency_ms
        self.fail_next = fail_next

    @staticmethod
    def pin_scenario(frame_hash: str, *, label: str, confidence: float) -> None:
        """Bind a fixture hash to a known outcome for the demo runbook."""
        if label not in DEFECT_LABELS:
            raise ValueError(f"unknown defect label: {label}")
        _PINNED_SCENARIOS[frame_hash] = (label, confidence)

    @staticmethod
    def clear_pins() -> None:
        _PINNED_SCENARIOS.clear()

    async def _infer(self, request: DetectionRequest) -> tuple[Prediction, ...]:
        if self.fail_next:
            self.fail_next = False
            raise DetectorUnavailableError("simulated detector failure")

        await asyncio.sleep(self._simulated_latency_ms / 1000.0)

        pinned = _PINNED_SCENARIOS.get(request.frame_hash)
        if pinned is not None:
            label, confidence = pinned
            return self._distribution(primary=label, primary_confidence=confidence)

        seed = hashlib.sha256(
            f"{request.frame_hash}|{request.station_id}|{request.product_sku}".encode()
        ).digest()
        # Two independent bytes: one selects the class, one sets confidence.
        label = DEFECT_LABELS[seed[0] % len(DEFECT_LABELS)]
        confidence = 0.40 + (seed[1] / 255.0) * 0.59
        return self._distribution(primary=label, primary_confidence=round(confidence, 4))

    def _distribution(self, *, primary: str, primary_confidence: float) -> tuple[Prediction, ...]:
        """Emit the primary label plus a residual, so downstream code sees a real distribution."""
        residual_label = NO_DEFECT_LABEL if primary != NO_DEFECT_LABEL else "surface_scratch"
        residual_confidence = round(max(0.0, 1.0 - primary_confidence), 4)
        box = (0.31, 0.28, 0.62, 0.55) if primary != NO_DEFECT_LABEL else None
        return (
            Prediction(
                label=primary,
                confidence=primary_confidence,
                threshold=self.decision_threshold,
                bounding_box=box,
            ),
            Prediction(
                label=residual_label,
                confidence=residual_confidence,
                threshold=self.decision_threshold,
            ),
        )
