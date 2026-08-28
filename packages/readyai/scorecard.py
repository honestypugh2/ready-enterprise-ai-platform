"""Scoring, the release gate and the remediation backlog."""

from __future__ import annotations

import json
from pathlib import Path

from readyai.model import (
    DIMENSIONS,
    Assessment,
    Dimension,
    DimensionScore,
    GateResult,
    MaturityLevel,
    ReadyBand,
)

RELEASE_GATE_MINIMUM = 60.0

# Non-compensating. A strong average across the other dimensions cannot buy a
# release when one of these is below Engineer, because that is exactly the
# failure the gate exists to catch.
CRITICAL_DIMENSIONS: frozenset[Dimension] = frozenset(
    {
        Dimension.RETRIEVAL,
        Dimension.EVALUATION,
        Dimension.DATA_GOVERNANCE,
        Dimension.TRUST,
    }
)


def score_assessment(assessment: Assessment) -> float:
    """Weighted total between 0 and 100."""
    return round(sum(score.weighted_score for score in assessment.scores), 2)


def evaluate_gate(assessment: Assessment) -> GateResult:
    """Apply the overall threshold and the per-dimension floors."""
    total = score_assessment(assessment)
    band = ReadyBand.for_score(total)
    reasons: list[str] = []

    if total < assessment.gate_minimum:
        reasons.append(
            f"overall score {total:.1f} is below the gate minimum {assessment.gate_minimum:.0f}"
        )

    critical = [s for s in assessment.scores if s.dimension in CRITICAL_DIMENSIONS]
    for score in sorted(critical, key=lambda s: s.dimension.value):
        if score.level < assessment.minimum_critical_level:
            reasons.append(
                f"{score.dimension.value} is at {score.level.name} "
                f"(minimum {assessment.minimum_critical_level.name})"
            )

    lowest = min(critical, key=lambda s: (int(s.level), s.dimension.value), default=None)
    return GateResult(
        passed=not reasons,
        overall_score=total,
        band=band,
        blocking_reasons=tuple(reasons),
        lowest_critical=lowest.dimension if lowest else None,
    )


def build_remediation_backlog(assessment: Assessment) -> tuple[DimensionScore, ...]:
    """Ordered work list: biggest weighted gain first, critical dimensions first.

    The ordering answers the only question a team actually has after a scoring
    session — which one do we fix before the next release.
    """

    def priority(score: DimensionScore) -> tuple[int, float, str]:
        is_critical = 0 if score.dimension in CRITICAL_DIMENSIONS else 1
        headroom = (
            (int(MaturityLevel.SCALE) - int(score.level)) / int(MaturityLevel.SCALE)
        ) * DIMENSIONS[score.dimension][0]
        return (is_critical, -headroom, score.dimension.value)

    return tuple(
        sorted(
            (s for s in assessment.scores if s.level < MaturityLevel.SCALE),
            key=priority,
        )
    )


def load_assessment(path: Path) -> Assessment:
    if not path.is_file():
        raise FileNotFoundError(f"assessment not found: {path}")
    return Assessment.model_validate(json.loads(path.read_text(encoding="utf-8")))


def render_scorecard(assessment: Assessment) -> str:
    """Text scorecard for a terminal or a CI summary."""
    gate = evaluate_gate(assessment)
    lines = [
        f"READY AI — {assessment.workload_name} ({assessment.workload_id})",
        f"assessed by {assessment.assessed_by} on {assessment.assessed_on.isoformat()} "
        f"| risk tier: {assessment.risk_tier}",
        "",
        f"{'dimension':<24}{'weight':>8}{'level':>10}{'weighted':>10}  evidence",
        "-" * 100,
    ]
    for score in sorted(assessment.scores, key=lambda s: s.dimension.value):
        evidence = score.evidence or score.gap or "—"
        lines.append(
            f"{score.dimension.value:<24}{score.weight * 100:>7.0f}%"
            f"{score.level.name:>10}{score.weighted_score:>10.2f}  {evidence[:44]}"
        )
    lines += [
        "-" * 100,
        f"{'overall':<24}{'100%':>8}{'':>10}{gate.overall_score:>10.2f}  band: {gate.band.value}",
        "",
        f"release gate: {'PASS' if gate.passed else 'FAIL'}",
    ]
    for reason in gate.blocking_reasons:
        lines.append(f"  - {reason}")
    lines.append(f"decision: {gate.band.decision}")

    backlog = build_remediation_backlog(assessment)
    if backlog:
        lines += ["", "remediation backlog (fix the first one before the next release):"]
        for index, score in enumerate(backlog[:5], start=1):
            owner = score.owner or "UNOWNED"
            due = score.due.isoformat() if score.due else "no date"
            lines.append(
                f"  {index}. {score.dimension.value} @ {score.level.name} "
                f"— {score.gap or 'gap not stated'} [{owner}, {due}]"
            )
    lines += [
        "",
        "READY AI is an original field framework, not an official Microsoft standard.",
    ]
    return "\n".join(lines)
