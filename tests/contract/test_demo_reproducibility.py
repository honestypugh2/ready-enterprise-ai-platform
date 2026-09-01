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
import re

import pytest
from tests.conftest import REPO_ROOT

from contracts.common import utcnow
from platform_config import PlatformSettings
from reasoning.prompts import OUTPUT_SCHEMA
from retrieval.local import LocalKnowledgeRetriever

KNOWLEDGE_DIR = REPO_ROOT / "data" / "knowledge"
CORPUS_FILES = sorted(KNOWLEDGE_DIR.glob("*.json"))
TALK_SCRIPT = REPO_ROOT / "docs" / "presentation-mapping" / "talk-script.md"

# Deliberately stale, and the only two that may be. SOP-311 is superseded
# guidance; REF-905 is an archived reference. Both exist so the freshness
# guard has something real to catch.
INTENTIONALLY_STALE = {"SOP-311", "REF-905"}


def test_the_reasoning_schema_requires_every_property_for_azure_strict_mode() -> None:
    assert set(OUTPUT_SCHEMA["required"]) == set(OUTPUT_SCHEMA["properties"])


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
        from cli.scenarios import load_scenarios  # noqa: PLC0415

        available = set(load_scenarios())
        shown = set(re.findall(r"reap demo run --scenario ([a-z-]+)", deck))
        assert shown <= available, f"the deck runs scenarios that do not exist: {shown - available}"
        assert "make azure-demo-preflight" in deck
        assert "http://127.0.0.1:5173" in deck

    def test_the_delivery_contract_matches_the_v5_deck(self, deck: str) -> None:
        main_slides = re.findall(r'<section[^>]+data-slide="S\d{2}"', deck)
        appendix_slides = re.findall(r'<section[^>]+data-slide="A\d{2}"', deck)
        assert len(main_slides) == 21
        assert len(appendix_slides) == 20

    def test_every_main_slide_has_its_talk_track_timing(self, deck: str) -> None:
        expected = {
            "S01": "0:00-0:45",
            "S02": "0:45-1:45",
            "S03": "1:45-3:00",
            "S04": "3:00-4:15",
            "S05": "4:15-5:15",
            "S06": "5:15-6:15",
            "S07": "6:15-7:30",
            "S08": "7:30-8:30",
            "S09": "8:30-9:30",
            "S10": "9:30-10:45",
            "S11": "10:45-12:00",
            "S12": "12:00-13:00",
            "S13": "13:00-14:00",
            "S14": "14:00-15:00",
            "S15": "15:00-16:00",
            "S16": "16:00-16:30",
            "S17": "16:30-17:00",
            "S18": "17:00-20:00",
            "S19": "20:00-21:00",
            "S20": "21:00-23:00",
            "S21": "23:00-25:00",
        }
        for slide, timing in expected.items():
            assert f'data-slide="{slide}" data-timing="{timing}"' in deck

    def test_every_timed_slide_has_the_complete_canonical_talk_track(self, deck: str) -> None:
        script = TALK_SCRIPT.read_text(encoding="utf-8")
        sections = re.findall(
            r"^## (S\d{2}) - (.+?) - (\d+:\d+-\d+:\d+)\n\n([\s\S]*?)(?=\n## |\Z)",
            script,
            flags=re.MULTILINE,
        )
        assert len(sections) == 21

        for slide_id, _title, timing, body in sections:
            slide = re.search(
                rf'<section[^>]+data-slide="{slide_id}"[^>]+data-timing="{timing}".*?</section>',
                deck,
                flags=re.DOTALL,
            )
            assert slide is not None, f"{slide_id} is missing or has drifted from timing {timing}"
            notes = re.search(
                rf'<aside class="notes" data-talk-track="{slide_id}">(.*?)</aside>',
                slide.group(0),
                flags=re.DOTALL,
            )
            assert notes is not None, f"{slide_id} has no synchronized speaker notes"
            rendered_words = re.findall(r"[A-Za-z0-9]+", re.sub(r"<[^>]+>", " ", notes.group(1)))
            source_words = re.findall(r"[A-Za-z0-9]+", body)
            assert len(rendered_words) >= len(source_words), (
                f"{slide_id} speaker notes are truncated: "
                f"{len(rendered_words)} rendered words for {len(source_words)} source words"
            )

    def test_the_v5_demo_window_requires_a_live_azure_path_and_an_honest_fallback(
        self, deck: str
    ) -> None:
        slides = [
            re.search(
                rf'<section[^>]+data-slide="S{number}".*?</section>',
                deck,
                flags=re.DOTALL,
            )
            for number in (16, 17, 18)
        ]
        assert all(slide is not None for slide in slides)
        content = " ".join(slide.group(0) for slide in slides if slide is not None)
        for required in (
            "Live Azure",
            "Azure AI Search",
            "Microsoft Foundry",
            "Application Insights",
            "deterministic",
            "scoped writer",
            "fallback",
            "audit ID",
        ):
            assert required.lower() in content.lower()

    def test_the_v5_slide_titles_are_in_order(self, deck: str) -> None:
        titles = (
            "Enterprise AI Architecture",
            "The Reframe",
            "The Anchor Diagram",
            "Component Fit",
            "Zoom: Action",
            "Field Patterns",
            "Zoom: Routing",
            "The Pivot",
            "Zoom: Retrieval",
            "Retrieval Internals",
            "Zoom: Evaluation",
            "Zoom: Authority",
            "Zoom: Security",
            "Failure Modes",
            "Zoom: Operations",
            "Governed Replenishment",
            "Demo Architecture",
            "Demo Walkthrough",
            "Reusable Assets",
            "The Framework",
            "Take This Back",
        )
        offsets = [deck.index(f'data-title="{title}"') for title in titles]
        assert offsets == sorted(offsets)

    def test_the_v5_architecture_slides_preserve_their_source_content(self, deck: str) -> None:
        required_by_slide = {
            "S02": (
                "Capability is not the constraint. Accountability is.",
                "what evidence permits a release",
            ),
            "S03": (
                "Foundry Agent Service",
                "If someone photographs one slide today, this is the one.",
            ),
            "S04": (
                "CNN / YOLO on edge GPU",
                "Task fit beats model size. The constraint that dominates chooses the component.",
            ),
            "S05": (
                "SOP, tolerance table and defect history",
                "The detector produces a signal. It cannot decide what the business does next.",
            ),
            "S06": (
                "The model scores",
                "Production AI combines predictive and generative.",
            ),
            "S07": (
                "route_id · cost · trace",
                "Re-benchmark before any route change.",
            ),
            "S09": (
                "The agentic variant",
                "Build a simple set and a complex set before changing topology.",
            ),
        }
        normalized_deck = re.sub(r"\s+", " ", deck)
        for slide_id, required_phrases in required_by_slide.items():
            match = re.search(
                rf'<section[^>]+data-slide="{slide_id}".*?</section>',
                normalized_deck,
            )
            assert match is not None
            for phrase in required_phrases:
                assert phrase.lower() in match.group(0).lower(), (
                    f"{slide_id} no longer preserves the v5 source phrase: {phrase}"
                )

    def test_every_slide_preserves_defining_v5_source_content(self, deck: str) -> None:
        required_by_slide = {
            "S01": ("principal engineers", "The model creates capability"),
            "S02": ("which data is authoritative", "what evidence permits a release"),
            "S03": ("Foundry Agent Service", "Fabric · OneLake"),
            "S04": ("Component class", "release gate"),
            "S05": ("tolerance table", "system of record"),
            "S06": ("The model scores · rules decide", "Safety-critical logic"),
            "S07": ("route_id · cost · trace", "Re-benchmark before any route change"),
            "S08": ("Fluency without a source", "better prompt or a bigger model"),
            "S09": ("query-time entitlement", "agentic variant"),
            "S10": ("cached chunks", "Who is entitled to see it"),
            "S11": ("adversarial regressions", "Version evaluation datasets like code"),
            "S12": ("cannot read corpus", "Revocation means one role"),
            "S13": ("retrieved or tool-returned content", "tested disaster recovery"),
            "S14": ("Blast radius", "Tiered fallback + circuit breaker"),
            "S15": ("human correction cost", "workload, route, and tenant"),
            "S16": ("warehouse-replenishment-ai-demo", "field service"),
            "S17": ("Nothing here is optional", "action correctness"),
            "S18": ("Keep two frames ready", "correlation ID"),
            "S19": ("writer failover", "benchmark-driven routing"),
            "S20": ("0 Absent", "High-impact actions demand stricter thresholds"),
            "S21": ("task completion", "one job, identity, and permitted action"),
            "A00": ("A15\u2013A19 · Moved", "None were deleted"),
            "A01": ("foundry-copilot-hr-policy-knowledge", "Copilot Studio"),
            "A02": ("foundry-workload-studio", "portfolio evidence"),
            "A03": ("warehouse-replenishment-ai-demo", "writer failover"),
            "A04": ("azureml-infra-foundation", "infrastructure as code"),
            "A05": ("hybrid-router-workshop", "response carries its route decision"),
            "A06": ("Sensitive-operation consent", "rejected-call review"),
            "A07": ("independent release cadence", "One agent per organisational role"),
            "A08": ("private DNS and endpoints", "tested DR path"),
            "A09": ("record-to-answer path", "Does deletion reach indexes and traces"),
            "A10": ("human correction time", "manual process"),
            "A11": ("Fraud / recommender", "residency, offline operation"),
            "A12": ("product owner", "Stop conditions"),
            "A13": ("Salesforce Agentforce", "not a feature scorecard"),
            "A14": ("Foundry IQ", "offline and online gates"),
            "A15": ("governed · owned · authoritative · refreshed", "rung 7"),
            "A16": ("Agent runtime", "Nothing in the chain is decorative"),
            "A17": ("Calibrated error and reproducibility", "cloud reasoning stays outside"),
            "A18": ("Shared by all three", "No motion succeeds alone"),
            "A19": ("Privilege escalation", "cannot cross the production boundary"),
        }
        normalized_deck = re.sub(r"\s+", " ", deck)
        for slide_id, required_phrases in required_by_slide.items():
            match = re.search(
                rf'<section[^>]+data-slide="{slide_id}".*?</section>',
                normalized_deck,
            )
            assert match is not None, f"the v5 slide {slide_id} is missing"
            for phrase in required_phrases:
                assert phrase.lower() in match.group(0).lower(), (
                    f"{slide_id} no longer preserves defining v5 source content: {phrase}"
                )

    def test_architecture_claims_are_rendered_as_diagrams(self, deck: str) -> None:
        for diagram in (
            "enterprise-platform",
            "action-flow",
            "model-routing",
            "hybrid-retrieval",
            "continuous-evaluation",
            "tool-authority",
            "security-topology",
            "observability-trace",
            "demo-architecture",
        ):
            assert f'data-diagram="{diagram}"' in deck

    def test_the_deck_preserves_the_source_documents_core_claims(self, deck: str) -> None:
        normalized_deck = re.sub(r"\s+", " ", deck).lower()
        required_claims = (
            "The model creates capability; the platform creates accountability.",
            "Model intent is never proof of user authorization.",
            "READY AI is an original field framework",
            "not an official Microsoft standard",
            "overall score of at least 60",
            "no critical dimension below Level 2",
        )
        for claim in required_claims:
            assert claim.lower() in normalized_deck

    def test_field_positioning_consumption_and_external_architecture_sources_are_explicit(
        self, deck: str
    ) -> None:
        normalized_deck = re.sub(r"\s+", " ", deck).lower()
        for required_phrase in (
            "AI Apps, Data, and Infrastructure meet at the release gate",
            "Consumption map:",
            "Field positioning:",
            "Microsoft reference: Azure AI Landing Zones",
            "Microsoft reference: MLOps v2 architecture",
            "Microsoft reference: Azure API Management Landing Zone Architecture",
            "fails the build when it no longer holds",
        ):
            assert required_phrase.lower() in normalized_deck


@pytest.fixture
def policy_version(settings: PlatformSettings) -> str:
    from policy_engine import PolicyEngine  # noqa: PLC0415

    return PolicyEngine.from_path(settings.governance.policy_path).version


def test_the_knowledge_directory_is_where_the_tests_think_it_is() -> None:
    assert KNOWLEDGE_DIR.is_dir()
    assert CORPUS_FILES, "no corpus files found; the parametrised tests above would pass vacuously"
