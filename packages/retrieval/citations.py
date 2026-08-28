"""Citation validation.

Displaying a citation is a user-interface feature. Validating one is an
architectural control, because a model can produce a marker pointing at a
document that does not support the sentence it is attached to, and a reader who
trusts the marker will never check.

Two gates, deliberately different in cost:

* **Runtime** — cheap lexical support, run on every request, tuned to catch
  gross mismatch and invented sources.
* **Release** — semantic entailment in the evaluation harness, where a model
  grader is affordable and latency does not matter.

Cheap gate at runtime, expensive gate at release.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from contracts.reasoning import Citation
from contracts.retrieval import RetrievedItem

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-]{2,}")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Marker for a claim grounded in the detection record rather than the corpus.
DETECTION_REF = "detection"

# Sentences that assert something checkable. Conservative on purpose so that
# hedging text is not flagged.
_CLAIM_HINTS = frozenset(
    {"is", "are", "was", "were", "must", "requires", "exceeds", "equals", "shall"}
)


@dataclass(frozen=True, slots=True)
class CitationIssue:
    kind: str  # unknown_reference | weak_support | uncited_claim
    detail: str
    citation_ref: str | None = None
    support: float | None = None


@dataclass(slots=True)
class CitationReport:
    """The evidence both the runtime check and the release gate consume."""

    checked: int = 0
    supported: int = 0
    issues: list[CitationIssue] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.supported / self.checked if self.checked else 0.0

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def support_score(claim: str, passage: str) -> float:
    """Fraction of the claim's content tokens present in the cited passage."""
    claim_tokens = _tokens(claim)
    if not claim_tokens:
        return 1.0
    return len(claim_tokens & _tokens(passage)) / len(claim_tokens)


def validate_citations(
    *,
    citations: tuple[Citation, ...],
    evidence: tuple[RetrievedItem, ...],
    narrative: str = "",
    min_support: float = 0.30,
    require_citation_on_claims: bool = True,
    additional_refs: frozenset[str] = frozenset(),
) -> CitationReport:
    """Check that every marker resolves and every claim is attributable.

    ``additional_refs`` covers claims grounded in something other than a
    retrieved passage — most importantly the detection record itself, which is
    evidence but is not something the retriever returned.
    """
    report = CitationReport()
    by_ref = {item.citation_ref: item for item in evidence}

    for citation in citations:
        report.checked += 1
        item = by_ref.get(citation.citation_ref)
        if item is None:
            # A marker with no retrieved passage behind it: the answer invented
            # a source, which is the failure worth blocking on.
            report.issues.append(
                CitationIssue(
                    kind="unknown_reference",
                    detail=f"citation {citation.citation_ref} was not retrieved in this turn",
                    citation_ref=citation.citation_ref,
                )
            )
            continue

        score = support_score(citation.supports_claim, item.passage)
        if score < min_support:
            report.issues.append(
                CitationIssue(
                    kind="weak_support",
                    detail="cited passage does not lexically support the claim",
                    citation_ref=citation.citation_ref,
                    support=round(score, 3),
                )
            )
        else:
            report.supported += 1

    if require_citation_on_claims and narrative:
        attributable = {c.citation_ref for c in citations} | additional_refs
        for sentence in (s.strip() for s in _SENTENCE.split(narrative) if s.strip()):
            has_marker = any(f"[{ref}]" in sentence for ref in attributable)
            if not has_marker and _is_claim(sentence):
                report.issues.append(CitationIssue(kind="uncited_claim", detail=sentence[:200]))

    return report


def _is_claim(sentence: str) -> bool:
    words = set(sentence.lower().split())
    has_number = any(character.isdigit() for character in sentence)
    return has_number or bool(words & _CLAIM_HINTS)
