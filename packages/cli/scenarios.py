"""Demo scenario fixtures.

Scenarios pin the detector to a known output so the demonstration produces the
same defect, the same verdict and the same approval requirement on every
machine — including one with no network. The pinned values are fixtures, not
model performance, and nothing in this module should be read as an accuracy
claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contracts.common import Classification, content_hash
from contracts.detection import DetectionRequest
from detector.mock import DeterministicMockDetector
from platform_config.settings import REPO_ROOT

DEFAULT_SCENARIO_PATH = REPO_ROOT / "data" / "fixtures" / "demo-scenarios.json"


@dataclass(frozen=True, slots=True)
class DemoScenario:
    """One reproducible pass through the governed workflow."""

    id: str
    name: str
    narrative: str
    frame_seed: str
    line_id: str
    station_id: str
    product_sku: str
    batch_id: str
    classification: Classification
    batch_defect_count: int
    pinned_label: str
    pinned_confidence: float
    expects: dict[str, Any]

    @property
    def frame_hash(self) -> str:
        return content_hash(self.frame_seed.encode("utf-8"))

    def to_request(self) -> DetectionRequest:
        return DetectionRequest(
            line_id=self.line_id,
            station_id=self.station_id,
            product_sku=self.product_sku,
            batch_id=self.batch_id,
            frame_hash=self.frame_hash,
            classification=self.classification,
        )

    def pin(self) -> None:
        """Bind the fixture hash to its known outcome on the mock detector."""
        DeterministicMockDetector.pin_scenario(
            self.frame_hash, label=self.pinned_label, confidence=self.pinned_confidence
        )


def load_scenarios(path: Path | None = None) -> dict[str, DemoScenario]:
    """Load every scenario and pin it, so ordering of demo steps does not matter."""
    document = json.loads((path or DEFAULT_SCENARIO_PATH).read_text(encoding="utf-8"))
    scenarios: dict[str, DemoScenario] = {}
    for entry in document["scenarios"]:
        scenario = DemoScenario(
            id=entry["id"],
            name=entry["name"],
            narrative=entry["narrative"],
            frame_seed=entry["frame_seed"],
            line_id=entry["line_id"],
            station_id=entry["station_id"],
            product_sku=entry["product_sku"],
            batch_id=entry["batch_id"],
            classification=Classification(entry["classification"]),
            batch_defect_count=int(entry["batch_defect_count"]),
            pinned_label=entry["pinned_label"],
            pinned_confidence=float(entry["pinned_confidence"]),
            expects=dict(entry.get("expects", {})),
        )
        scenario.pin()
        scenarios[scenario.id] = scenario
    return scenarios


def get_scenario(scenario_id: str, *, path: Path | None = None) -> DemoScenario:
    scenarios = load_scenarios(path)
    if scenario_id not in scenarios:
        raise KeyError(
            f"unknown scenario '{scenario_id}'; available: {', '.join(sorted(scenarios))}"
        )
    return scenarios[scenario_id]
