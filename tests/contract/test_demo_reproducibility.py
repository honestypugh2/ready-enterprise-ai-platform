"""The demonstration must not change because time passed.

The repository claims the demo "produces the same result on every machine".
It did — but the knowledge corpus was dated with absolute timestamps, so
passages aged in real time and silently crossed their freshness SLO. A passage
that was fresh at one demo was stale at the next, `G003-stale-evidence` began
firing, and the disposition changed with it.

Reproducible across machines is not the same claim as reproducible across days,
and only the second one makes a demo safe to stand behind.
"""

from __future__ import annotations

import json

import pytest
from tests.conftest import REPO_ROOT

from contracts.common import utcnow
from platform_config import PlatformSettings
from retrieval.local import LocalKnowledgeRetriever

KNOWLEDGE_DIR = REPO_ROOT / "data" / "knowledge"
CORPUS_FILES = sorted(KNOWLEDGE_DIR.glob("*.json"))

# Deliberately stale, and the only two that may be. SOP-311 is superseded
# guidance; REF-905 is an archived reference. Both exist so the freshness
# guard has something real to catch.
INTENTIONALLY_STALE = {"SOP-311", "REF-905"}


def passages() -> list[tuple[str, dict[str, object]]]:
    entries: list[tuple[str, dict[str, object]]] = []
    for path in CORPUS_FILES:
        document = json.loads(path.read_text(encoding="utf-8"))
        entries.extend((path.name, entry) for entry in document["passages"])
    return entries


class TestCorpusCannotAgeInRealTime:
    def test_the_corpus_is_not_empty(self) -> None:
        """Guards the rest of this file against passing vacuously."""
        assert passages()

    @pytest.mark.parametrize(("filename", "entry"), passages(), ids=lambda v: str(v)[:40])
    def test_every_passage_declares_an_age_not_a_date(
        self, filename: str, entry: dict[str, object]
    ) -> None:
        """`age_days` holds constant; `updated_at` drifts with the calendar."""
        assert "age_days" in entry, (
            f"{filename}:{entry['source_id']} uses an absolute date. "
            "Use `age_days` so the fixture's age is the same on any day."
        )
        assert "updated_at" not in entry

    @pytest.mark.parametrize(("filename", "entry"), passages(), ids=lambda v: str(v)[:40])
    def test_freshness_is_a_deliberate_choice_not_an_accident(
        self, filename: str, entry: dict[str, object]
    ) -> None:
        source_id = str(entry["source_id"])
        age = int(entry["age_days"])  # type: ignore[call-overload]
        slo = int(entry.get("freshness_slo_days", 90))  # type: ignore[call-overload]

        if source_id in INTENTIONALLY_STALE:
            assert age > slo, f"{source_id} is meant to be stale but is inside its SLO"
        else:
            assert age <= slo, (
                f"{source_id} is {age}d old against a {slo}d SLO. Either it was "
                "meant to be stale — add it to INTENTIONALLY_STALE — or the age is wrong."
            )

    @pytest.mark.parametrize(("filename", "entry"), passages(), ids=lambda v: str(v)[:40])
    def test_fresh_passages_have_headroom(self, filename: str, entry: dict[str, object]) -> None:
        """A passage three days inside its SLO is a demo that breaks next week.

        This is the assertion that would have caught the original defect: MS-118
        sat 27 days into a 30-day SLO and would have gone stale mid-session.
        """
        source_id = str(entry["source_id"])
        if source_id in INTENTIONALLY_STALE:
            return
        age = int(entry["age_days"])  # type: ignore[call-overload]
        slo = int(entry.get("freshness_slo_days", 90))  # type: ignore[call-overload]
        assert age <= slo * 0.75, (
            f"{source_id} is at {age}/{slo} days — too close to its SLO to be stable."
        )


class TestRetrievalIsStableAcrossTime:
    async def test_a_passage_is_always_the_age_it_declares(
        self, settings: PlatformSettings
    ) -> None:
        """The property that makes the demo stable.

        `updated_at` is derived from the load time, so the age a passage
        presents is the age it declares — today, and on the morning of the
        session, and a year from now.
        """
        retriever = LocalKnowledgeRetriever(knowledge_dir=settings.retrieval.knowledge_dir)
        retriever.load()
        declared = {
            str(e["source_id"]): int(e["age_days"])  # type: ignore[call-overload]
            for _, e in passages()
        }

        now = utcnow()
        for document in retriever._documents:
            observed = (now - document.updated_at).days
            assert observed == declared[document.source_id], (
                f"{document.source_id} presents as {observed}d but declares "
                f"{declared[document.source_id]}d"
            )

    async def test_exactly_the_intended_passages_are_stale(
        self, settings: PlatformSettings
    ) -> None:
        retriever = LocalKnowledgeRetriever(knowledge_dir=settings.retrieval.knowledge_dir)
        retriever.load()
        now = utcnow()
        stale = {d.source_id for d in retriever._documents if d.is_stale(now=now)}
        assert stale == INTENTIONALLY_STALE

    async def test_two_loads_agree_on_freshness(self, settings: PlatformSettings) -> None:
        first = LocalKnowledgeRetriever(knowledge_dir=settings.retrieval.knowledge_dir)
        second = LocalKnowledgeRetriever(knowledge_dir=settings.retrieval.knowledge_dir)
        first.load()
        second.load()
        now = utcnow()
        assert {d.source_id for d in first._documents if d.is_stale(now=now)} == {
            d.source_id for d in second._documents if d.is_stale(now=now)
        }


class TestDeckClaimsMatchTheSystem:
    """The deck makes factual claims about this repository.

    It is tracked in git and shown to an audience beside a live terminal, so a
    stale figure on a slide is contradicted on screen. The deck's claims are
    enforced the same way every other claim here is.
    """

    DECK = REPO_ROOT / "presentation" / "index.html"

    @pytest.fixture
    def deck(self) -> str:
        if not self.DECK.is_file():
            pytest.skip("no deck in this working tree")
        return self.DECK.read_text(encoding="utf-8")

    def test_the_deck_quotes_the_current_policy_version(
        self, deck: str, policy_version: str
    ) -> None:
        assert f">{policy_version}<" in deck or policy_version in deck, (
            f"the deck does not mention policy version {policy_version}; "
            "captured output on a slide has drifted from the repository"
        )

    def test_the_deck_quotes_no_superseded_policy_version(
        self, deck: str, policy_version: str
    ) -> None:
        import re  # noqa: PLC0415

        quoted = set(re.findall(r"\b\d+\.\d+\.\d+\b", deck))
        governance = {v for v in quoted if v.startswith("2.")}
        assert governance <= {policy_version}, (
            f"the deck quotes superseded policy versions {governance - {policy_version}}; "
            f"the repository is at {policy_version}"
        )

    def test_every_command_the_deck_demonstrates_exists(self, deck: str) -> None:
        import re  # noqa: PLC0415

        from cli.scenarios import load_scenarios  # noqa: PLC0415

        available = set(load_scenarios())
        shown = set(re.findall(r"reap demo run --scenario ([a-z-]+)", deck))
        assert shown, "the deck no longer demonstrates any scenario"
        assert shown <= available, f"the deck runs scenarios that do not exist: {shown - available}"


@pytest.fixture
def policy_version(settings: PlatformSettings) -> str:
    from policy_engine import PolicyEngine  # noqa: PLC0415

    return PolicyEngine.from_path(settings.governance.policy_path).version


def test_the_knowledge_directory_is_where_the_tests_think_it_is() -> None:
    assert KNOWLEDGE_DIR.is_dir()
    assert CORPUS_FILES, "no corpus files found; the parametrised tests above would pass vacuously"
