"""Specialized model plane.

The detector produces a signal. It cannot decide what the business does next,
and nothing in this package is capable of doing so.

Three implementations sit behind one protocol:

* ``DeterministicMockDetector`` — the default. No weights, no network, fully
  reproducible from the input hash, so a demo produces the same defect every
  time and a test never flakes.
* ``OnnxDetector`` — a locally executed ONNX graph the operator supplies, for
  teams that want a real CNN without a cloud dependency.
* ``AzureMLEndpointDetector`` — an Azure Machine Learning managed online
  endpoint, which is where a production CNN/YOLO workload actually lives.

Moving between them changes one configuration value and nothing else. That
substitutability is the point of the plane.

The defect taxonomy itself lives in ``contracts.taxonomy``, not here. The
policy engine and the reasoning plane both need that vocabulary, and a shared
vocabulary that lives inside one plane is a boundary violation waiting to be
rationalised away.
"""

from detector.aml import AzureMLEndpointDetector
from detector.base import BaseDetector, Detector, DetectorUnavailableError
from detector.factory import build_detector
from detector.mock import DeterministicMockDetector

__all__ = [
    "AzureMLEndpointDetector",
    "BaseDetector",
    "Detector",
    "DetectorUnavailableError",
    "DeterministicMockDetector",
    "build_detector",
]
