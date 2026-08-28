"""Detector selection.

The factory reads configuration and returns a detector. Nothing above this line
knows which implementation it is talking to, which is what lets a workload move
from mock to ONNX to an Azure ML endpoint without touching the workflow.
"""

from __future__ import annotations

from typing import Any

from detector.base import Detector, DetectorUnavailableError
from detector.mock import DeterministicMockDetector
from platform_config import DetectorSettings, ExecutionMode, PlatformSettings


def build_detector(settings: PlatformSettings, *, credential: Any | None = None) -> Detector:
    """Construct the configured detector, or fail loudly at start-up."""
    config: DetectorSettings = settings.detector

    if config.provider == "mock":
        return DeterministicMockDetector(
            model_name=config.model_name,
            model_version=config.model_version,
            decision_threshold=config.decision_threshold,
        )

    if config.provider == "onnx":
        from detector.onnx import OnnxDetector  # noqa: PLC0415  (optional extra)

        if config.onnx_model_path is None:
            raise DetectorUnavailableError(
                "REAP_DETECTOR_ONNX_MODEL_PATH must be set when provider=onnx"
            )
        return OnnxDetector(
            model_path=config.onnx_model_path,
            model_name=config.model_name,
            model_version=config.model_version,
            decision_threshold=config.decision_threshold,
        )

    if config.provider == "aml":
        if settings.mode is ExecutionMode.LOCAL_MOCK:
            raise DetectorUnavailableError(
                "provider=aml requires REAP_MODE=azure_dev or production"
            )
        from detector.aml import AzureMLEndpointDetector  # noqa: PLC0415  (optional extra)

        if not config.aml_endpoint_url:
            raise DetectorUnavailableError(
                "REAP_DETECTOR_AML_ENDPOINT_URL must be set when provider=aml"
            )
        return AzureMLEndpointDetector(
            scoring_uri=config.aml_endpoint_url,
            model_name=config.model_name,
            model_version=config.model_version,
            deployment_name=config.aml_deployment_name,
            decision_threshold=config.decision_threshold,
            timeout_ms=config.timeout_ms,
            max_attempts=config.max_attempts,
            credential=credential,
        )

    raise DetectorUnavailableError(f"unknown detector provider: {config.provider}")
