"""Evaluation harness.

Turns a release decision into a calculation. Runs a versioned dataset through
the system under test, applies the grader suite, compares each result against
its threshold, writes a structured report, and returns a single boolean the
pipeline uses to proceed or stop.

The boolean is what the pipeline needs; the report is what the humans need. It
names the dataset version, the threshold per grader, the mean score and the
identifier of every failing case, which turns the release conversation into a
review of specific failures rather than an argument about whether the system
feels ready.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean

from contracts.common import utcnow
from evaluation.graders import Grader, GradeResult
from evaluation.models import EvalCase, EvalDataset, SystemOutput

RunSystem = Callable[[EvalCase], Awaitable[SystemOutput]]


@dataclass(frozen=True, slots=True)
class GraderSummary:
    grader: str
    threshold: float
    blocking: bool
    mean_score: float
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(slots=True)
class EvaluationReport:
    """The artifact attached to the release evidence bundle."""

    dataset_id: str
    dataset_version: str
    case_count: int
    release_gate_passed: bool
    summaries: tuple[GraderSummary, ...]
    grades: tuple[GradeResult, ...]
    non_blocking_failures: tuple[str, ...] = ()
    generated_at: datetime = field(default_factory=utcnow)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_utc": self.generated_at.isoformat(),
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "case_count": self.case_count,
            "release_gate_passed": self.release_gate_passed,
            "duration_ms": round(self.duration_ms, 2),
            "summary": {
                s.grader: {
                    "threshold": s.threshold,
                    "blocking": s.blocking,
                    "mean_score": round(s.mean_score, 4),
                    "failures": list(s.failures),
                }
                for s in self.summaries
            },
            "non_blocking_failures": list(self.non_blocking_failures),
            "grades": [asdict(g) for g in self.grades],
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    def render_text(self) -> str:
        lines = [
            f"dataset {self.dataset_id} v{self.dataset_version} — {self.case_count} cases",
            f"release gate: {'PASS' if self.release_gate_passed else 'FAIL'}",
            "",
        ]
        for summary in self.summaries:
            marker = "PASS" if summary.passed else ("FAIL" if summary.blocking else "WARN")
            gate = "blocking" if summary.blocking else "reported only"
            lines.append(
                f"  [{marker}] {summary.grader:24s} mean={summary.mean_score:.3f} "
                f"threshold={summary.threshold:.2f} ({gate})"
            )
            for case_id in summary.failures:
                detail = next(
                    (
                        g.detail
                        for g in self.grades
                        if g.case_id == case_id and g.grader == summary.grader
                    ),
                    "",
                )
                lines.append(f"          - {case_id}: {detail}")
        return "\n".join(lines)


class EvaluationHarness:
    """Runs a dataset and decides on release."""

    def __init__(
        self,
        graders: Sequence[Grader],
        run_system: RunSystem,
        *,
        max_concurrency: int = 8,
    ) -> None:
        if not graders:
            raise ValueError("at least one grader is required")
        self._graders = list(graders)
        self._run_system = run_system
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run(self, dataset: EvalDataset) -> EvaluationReport:
        started = time.perf_counter()
        results = await asyncio.gather(*(self._evaluate_case(case) for case in dataset.cases))
        grades = tuple(grade for group in results for grade in group)

        summaries: list[GraderSummary] = []
        for grader in self._graders:
            relevant = [g for g in grades if g.grader == grader.name]
            summaries.append(
                GraderSummary(
                    grader=grader.name,
                    threshold=grader.threshold,
                    blocking=grader.blocking,
                    mean_score=mean([g.score for g in relevant]) if relevant else 0.0,
                    failures=tuple(g.case_id for g in relevant if not g.passed),
                )
            )

        blocking_failed = any(not s.passed for s in summaries if s.blocking)
        non_blocking = tuple(
            f"{s.grader}:{case_id}" for s in summaries if not s.blocking for case_id in s.failures
        )

        return EvaluationReport(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            case_count=len(dataset.cases),
            release_gate_passed=not blocking_failed,
            summaries=tuple(summaries),
            grades=grades,
            non_blocking_failures=non_blocking,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    async def _evaluate_case(self, case: EvalCase) -> list[GradeResult]:
        async with self._semaphore:
            try:
                output = await self._run_system(case)
            except Exception as exc:
                # The system failing to produce an output is itself a failure of
                # every grader, not an absence of data.
                return [
                    GradeResult(
                        grader=grader.name,
                        case_id=case.case_id,
                        score=0.0,
                        passed=False,
                        detail=f"system error: {type(exc).__name__}: {exc}",
                        blocking=grader.blocking,
                    )
                    for grader in self._graders
                ]
        return list(await asyncio.gather(*(grader.grade(case, output) for grader in self._graders)))
