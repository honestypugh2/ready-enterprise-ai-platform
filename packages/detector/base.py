"""Detector protocol and the shared safety behaviour every implementation inherits."""

from __future__ import annotations

import abc
import time
from typing import Protocol, runtime_checkable

from contracts.common import ExecutionLocation, Provenance
from contracts.detection import DetectionRequest, DetectionResult, Prediction
from contracts.errors import UpstreamUnavailableError


class DetectorUnavailableError(UpstreamUnavailableError):
    """The detector could not produce a prediction within its budget."""

    plane = "detector"


@runtime_checkable
class Detector(Protocol):
    """What every detector must offer, regardless of where it executes."""

    model_name: str
    model_version: str
    execution_location: ExecutionLocation

    async def detect(self, request: DetectionRequest, *, correlation_id: str) -> DetectionResult:
        """Infer, or raise ``DetectorUnavailableError``.

        Implementations must never invent a prediction on failure. An absent
        signal is recoverable; a fabricated one is not.
        """
        ...

    async def healthy(self) -> bool: ...


class BaseDetector(abc.ABC):
    """Common assembly of the auditable result so every adapter records the same fields."""

    model_name: str
    model_version: str
    execution_location: ExecutionLocation

    def __init__(self, *, decision_threshold: float) -> None:
        if not 0.0 <= decision_threshold <= 1.0:
            raise ValueError("decision_threshold must be within [0, 1]")
        self.decision_threshold = decision_threshold

    @abc.abstractmethod
    async def _infer(self, request: DetectionRequest) -> tuple[Prediction, ...]:
        """Return raw predictions. Ranking and record assembly happen in ``detect``."""

    async def healthy(self) -> bool:
        return True

    async def detect(self, request: DetectionRequest, *, correlation_id: str) -> DetectionResult:
        started = time.perf_counter()
        predictions = await self._infer(request)
        latency_ms = (time.perf_counter() - started) * 1000.0

        if not predictions:
            raise DetectorUnavailableError(
                "detector returned no predictions", correlation_id=correlation_id
            )

        primary = max(predictions, key=lambda p: p.confidence)
        return DetectionResult(
            request_id=request.request_id,
            correlation_id=correlation_id,
            model_name=self.model_name,
            model_version=self.model_version,
            input_hash=request.frame_hash,
            predictions=predictions,
            primary_label=primary.label,
            primary_confidence=primary.confidence,
            decision_threshold=self.decision_threshold,
            latency_ms=latency_ms,
            execution_location=self.execution_location,
            provenance=Provenance(
                producer=self.model_name,
                producer_version=self.model_version,
                execution_location=self.execution_location,
                input_hashes=(request.frame_hash,),
            ),
        )
