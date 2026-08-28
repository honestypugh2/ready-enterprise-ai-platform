"""Local ONNX detector.

Present so that "run a real CNN" does not require a cloud subscription. It
loads a model the operator supplies; the repository ships **no** weights and
downloads none, because a demo that silently fetches unverified model artifacts
is a supply-chain problem wearing a convenience costume.

``onnxruntime``, ``numpy`` and ``pillow`` are optional extras. Import failures
surface as a clear configuration error rather than a stack trace at request
time.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

from contracts.common import ExecutionLocation
from contracts.detection import DetectionRequest, Prediction
from contracts.taxonomy import DEFECT_LABELS
from detector.base import BaseDetector, DetectorUnavailableError


class OnnxDetector(BaseDetector):
    """Runs a supplied ONNX classification graph on CPU."""

    def __init__(
        self,
        *,
        model_path: Path,
        model_name: str,
        model_version: str,
        labels: tuple[str, ...] = DEFECT_LABELS,
        decision_threshold: float = 0.62,
        input_size: tuple[int, int] = (224, 224),
    ) -> None:
        super().__init__(decision_threshold=decision_threshold)
        if not model_path.is_file():
            raise DetectorUnavailableError(f"ONNX model not found at {model_path}")
        self.model_path = model_path
        self.model_name = model_name
        self.model_version = model_version
        self.labels = labels
        self.execution_location = ExecutionLocation.LOCAL_PROCESS
        self._input_size = input_size
        self._session: Any | None = None

    def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        try:
            import onnxruntime  # noqa: PLC0415  (optional extra)
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise DetectorUnavailableError(
                "onnxruntime is not installed; run `uv sync --extra onnx`"
            ) from exc
        self._session = onnxruntime.InferenceSession(
            str(self.model_path), providers=["CPUExecutionProvider"]
        )
        return self._session

    async def healthy(self) -> bool:
        try:
            self._ensure_session()
        except DetectorUnavailableError:
            return False
        return True

    @staticmethod
    def _read_frame(frame_path: Path) -> bytes:
        """Blocking file read, kept off the event loop by the caller."""
        if not frame_path.is_file():
            raise DetectorUnavailableError(f"frame not readable at {frame_path}")
        return frame_path.read_bytes()

    async def _infer(self, request: DetectionRequest) -> tuple[Prediction, ...]:
        try:
            import numpy as np  # noqa: PLC0415  (optional extra)
            from PIL import Image  # noqa: PLC0415  (optional extra)
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise DetectorUnavailableError(
                "numpy/pillow are not installed; run `uv sync --extra onnx`"
            ) from exc

        if not request.frame_uri:
            raise DetectorUnavailableError("ONNX detector requires a frame_uri")
        frame_path = Path(request.frame_uri)
        image_bytes = await asyncio.to_thread(self._read_frame, frame_path)

        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb = image.convert("RGB").resize(self._input_size)
            array = np.asarray(rgb, dtype=np.float32) / 255.0
        tensor = np.transpose(array, (2, 0, 1))[np.newaxis, ...]

        session = self._ensure_session()
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: tensor})
        logits = np.asarray(outputs[0]).reshape(-1)
        if logits.size != len(self.labels):
            raise DetectorUnavailableError(
                f"model emitted {logits.size} logits but {len(self.labels)} labels are configured"
            )

        exponentials = np.exp(logits - logits.max())
        probabilities = exponentials / exponentials.sum()
        ranked = sorted(zip(self.labels, probabilities, strict=True), key=lambda x: -float(x[1]))
        return tuple(
            Prediction(
                label=label,
                confidence=round(float(score), 4),
                threshold=self.decision_threshold,
            )
            for label, score in ranked[:3]
        )
