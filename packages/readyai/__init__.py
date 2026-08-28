"""READY AI production-readiness framework.

READY AI is an **original field framework** created for the *Beyond the Agent*
session. **It is not an official Microsoft standard**, it is not a product
feature, and where it overlaps with published Microsoft guidance the published
guidance takes precedence. It should be introduced that way in a room and
adapted to an organisation's own risk model rather than adopted unchanged.

It exists to turn "are we ready?" from a feeling into a calculation:

* five weighted dimensions plus a trust overlay,
* five evidence-based maturity levels,
* a **non-compensating** release gate, so a strong average cannot hide a
  critical gap.

Scoring is evidence-based rather than aspirational. If the artifact named in
the dimension does not exist, the level is not claimed — which is why
``DimensionScore`` rejects a level above Explore that cites no evidence.
"""

from readyai.model import (
    DIMENSIONS,
    Assessment,
    Dimension,
    DimensionScore,
    GateResult,
    MaturityLevel,
    ReadyBand,
)
from readyai.scorecard import (
    CRITICAL_DIMENSIONS,
    RELEASE_GATE_MINIMUM,
    build_remediation_backlog,
    evaluate_gate,
    load_assessment,
    score_assessment,
)

__all__ = [
    "CRITICAL_DIMENSIONS",
    "DIMENSIONS",
    "RELEASE_GATE_MINIMUM",
    "Assessment",
    "Dimension",
    "DimensionScore",
    "GateResult",
    "MaturityLevel",
    "ReadyBand",
    "build_remediation_backlog",
    "evaluate_gate",
    "load_assessment",
    "score_assessment",
]
