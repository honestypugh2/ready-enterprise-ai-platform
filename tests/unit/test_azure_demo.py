"""Contracts for preparing the live Azure demonstration."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from cli.azure_demo import index_demo_corpus, load_demo_documents, run_preflight
from platform_config import PlatformSettings
from tests.conftest import REPO_ROOT


def test_the_default_search_corpus_excludes_adversarial_passages() -> None:
    observed_at = datetime(2026, 1, 1, tzinfo=UTC)
    documents = load_demo_documents(REPO_ROOT / "data" / "knowledge", now=observed_at)
    declared_ages: dict[str, int] = {}
    for path in (REPO_ROOT / "data" / "knowledge").glob("*.json"):
        source = json.loads(path.read_text())
        if source.get("corpus_id") != "adversarial-corpus":
            declared_ages.update(
                {entry["source_id"]: entry["age_days"] for entry in source["passages"]}
            )

    assert documents
    assert all(not document["source_id"].startswith("ADV-") for document in documents)
    for document in documents:
        updated_at = datetime.fromisoformat(document["updated_at"])
        assert (observed_at - updated_at).days == declared_ages[document["source_id"]]


def test_adversarial_passages_require_an_explicit_opt_in() -> None:
    documents = load_demo_documents(
        REPO_ROOT / "data" / "knowledge",
        include_adversarial=True,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert any(document["source_id"].startswith("ADV-") for document in documents)


def test_indexing_refuses_the_default_local_mode(settings: PlatformSettings) -> None:
    with pytest.raises(ValueError, match="REAP_MODE=azure_dev"):
        index_demo_corpus(settings)


async def test_preflight_reports_local_mode_without_requesting_a_credential(
    settings: PlatformSettings,
) -> None:
    checks = await run_preflight(settings)

    assert checks[0].name == "azure mode"
    assert not checks[0].ok
    assert all(check.name != "Azure credential" for check in checks)
