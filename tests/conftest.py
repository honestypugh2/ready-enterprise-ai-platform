"""Shared fixtures.

Two rules hold across every suite:

* **Deterministic by default.** No test depends on wall-clock timing, network
  access, or a random seed the test does not control. A flaky governance test
  gets disabled, and a disabled governance test is a missing control.
* **Isolated by default.** Settings are cached per process, so every test that
  touches configuration resets the cache. Otherwise the first test to read
  settings silently decides the mode for the rest of the run.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from approvals import ApprovalService, InMemoryApprovalStore
from cli.scenarios import DemoScenario, load_scenarios
from connectors import MockEnterpriseConnector, ScopedWriter, mock_erp
from contracts.action import ActionKind
from contracts.common import (
    Classification,
    ExecutionLocation,
    Provenance,
    content_hash,
    new_id,
)
from contracts.detection import DetectionRequest, DetectionResult, Prediction
from contracts.retrieval import RetrievalResult, RetrievalStrategy, RetrievedItem
from detector import DeterministicMockDetector
from platform_config import PlatformSettings, get_settings, reset_settings_cache
from policy_engine import PolicyEngine
from security.identity import IdentityContext
from workflows import PlatformAssembly, build_platform

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

# The marker documentation in pyproject.toml promises these are skipped without
# an opt-in. Implemented here so the promise is executable rather than a comment.
_OPT_IN_MARKERS = {"integration": "REAP_RUN_INTEGRATION", "load": "REAP_RUN_LOAD"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for marker, variable in _OPT_IN_MARKERS.items():
        if os.environ.get(variable) == "1":
            continue
        skip = pytest.mark.skip(reason=f"set {variable}=1 to run {marker} tests")
        for item in items:
            # Markers only. `item.keywords` also matches the containing package
            # name, which would silently skip every offline test under
            # tests/integration/.
            if item.get_closest_marker(marker) is not None:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Force local mock mode and a scratch state directory for every test."""
    for key in [k for k in os.environ if k.startswith("REAP_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("REAP_MODE", "local_mock")
    monkeypatch.setenv("REAP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("REAP_OTEL_CONSOLE_EXPORTER", "false")
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def settings() -> PlatformSettings:
    return get_settings()


@pytest.fixture
def identity() -> IdentityContext:
    return IdentityContext.local_demo_operator()


@pytest.fixture
def approver() -> IdentityContext:
    return IdentityContext.local_demo_approver("maintenance_lead")


@pytest.fixture
def scenarios() -> dict[str, DemoScenario]:
    return load_scenarios()


@pytest.fixture
def policy(settings: PlatformSettings) -> PolicyEngine:
    return PolicyEngine.from_path(settings.governance.policy_path)


@pytest.fixture
def detector() -> DeterministicMockDetector:
    return DeterministicMockDetector()


@pytest.fixture
def approvals() -> ApprovalService:
    return ApprovalService(store=InMemoryApprovalStore(), expiry_hours=8)


@pytest.fixture
def connector() -> MockEnterpriseConnector:
    return mock_erp()


@pytest.fixture
def writer(connector: MockEnterpriseConnector, approvals: ApprovalService) -> ScopedWriter:
    """A writer with dry run OFF, so tests exercise the real write path."""
    return ScopedWriter(connector=connector, approvals=approvals, dry_run_default=False)


@pytest.fixture
def assembly(settings: PlatformSettings) -> PlatformAssembly:
    return build_platform(settings, recording_bus=True)


@pytest.fixture
async def api_client() -> AsyncIterator[object]:
    """FastAPI test client with a fully wired platform behind it."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from api.main import create_app  # noqa: PLC0415

    with TestClient(create_app()) as client:
        yield client


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def make_request(
    *,
    label_seed: str = "unit-test-frame",
    line_id: str = "DEMO-L1",
    station_id: str = "ST-07",
    product_sku: str = "SKU-88421",
    batch_id: str | None = "BATCH-TEST-01",
    classification: Classification = Classification.INTERNAL,
) -> DetectionRequest:
    return DetectionRequest(
        line_id=line_id,
        station_id=station_id,
        product_sku=product_sku,
        batch_id=batch_id,
        frame_hash=content_hash(label_seed.encode("utf-8")),
        classification=classification,
    )


def make_detection(
    *,
    label: str = "seal_gap",
    confidence: float = 0.88,
    threshold: float = 0.62,
    correlation_id: str | None = None,
) -> DetectionResult:
    """A detection result without going through a detector.

    Lets a policy test state exactly the signal it is about, rather than
    reverse-engineering a frame hash that happens to produce it.
    """
    residual = "no_defect" if label != "no_defect" else "surface_scratch"
    return DetectionResult(
        request_id=new_id("det"),
        correlation_id=correlation_id or new_id("corr"),
        model_name="surface-defect-detector",
        model_version="0.3.0-demo",
        input_hash=content_hash(f"{label}:{confidence}".encode()),
        predictions=(
            Prediction(label=label, confidence=confidence, threshold=threshold),
            Prediction(label=residual, confidence=round(1.0 - confidence, 4), threshold=threshold),
        ),
        primary_label=label,
        primary_confidence=confidence,
        decision_threshold=threshold,
        latency_ms=7.5,
        execution_location=ExecutionLocation.MOCK,
        provenance=Provenance(
            producer="surface-defect-detector",
            producer_version="0.3.0-demo",
            execution_location=ExecutionLocation.MOCK,
        ),
    )


def make_item(
    *,
    source_id: str = "MS-118",
    citation_ref: str = "MS-118",
    authority: str = "authoritative",
    classification: Classification = Classification.INTERNAL,
    access_groups: frozenset[str] = frozenset({"grp-manufacturing-all"}),
    age_days: int = 10,
    freshness_slo_days: int = 90,
    passage: str = "Seal gaps exceeding 0.4 mm require immediate quarantine.",
    score: float = 0.91,
) -> RetrievedItem:
    return RetrievedItem(
        source_id=source_id,
        source_title=f"{source_id} test passage",
        passage=passage,
        source_uri=f"https://example.invalid/{source_id}",
        version="1.0",
        updated_at=FIXED_NOW - timedelta(days=age_days),
        classification=classification,
        access_groups=access_groups,
        authority=authority,
        score=score,
        citation_ref=citation_ref,
        freshness_slo_days=freshness_slo_days,
    )


def make_evidence(
    *items: RetrievedItem,
    correlation_id: str = "corr_testtesttest",
    partial: bool = False,
    failures: tuple[str, ...] = (),
) -> RetrievalResult:
    return RetrievalResult(
        query_id=new_id("q"),
        correlation_id=correlation_id,
        strategy=RetrievalStrategy.HYBRID,
        items=items or (make_item(),),
        latency_ms=4.2,
        index_name="manufacturing-knowledge",
        index_version="1",
        partial=partial,
        failures=failures,
    )


__all__ = [
    "FIXED_NOW",
    "REPO_ROOT",
    "ActionKind",
    "make_detection",
    "make_evidence",
    "make_item",
    "make_request",
]
