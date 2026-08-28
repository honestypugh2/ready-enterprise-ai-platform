"""READY AI dimensions, levels and the assessment record."""

from __future__ import annotations

from datetime import date
from enum import IntEnum, StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Dimension(StrEnum):
    """Five weighted dimensions plus the overlay that is scored across them all."""

    RETRIEVAL = "retrieval_strategy"
    EVALUATION = "evaluation_framework"
    ARCHITECTURE = "architecture_design"
    DATA_GOVERNANCE = "data_governance"
    YIELD_OPERATIONS = "yield_operations"
    TRUST = "ai_trust_overlay"


class MaturityLevel(IntEnum):
    """Evidence standard per level. The gap that matters is 1 → 2.

    Explore is something a team did once. Engineer is something that happens
    automatically whether or not anyone remembers.
    """

    ABSENT = 0
    EXPLORE = 1
    ENGINEER = 2
    OPERATE = 3
    SCALE = 4


class ReadyBand(StrEnum):
    EXPLORE = "explore"
    ENGINEER = "engineer"
    OPERATE = "operate"
    SCALE = "scale"

    @classmethod
    def for_score(cls, score: float) -> ReadyBand:
        if score < 40:
            return cls.EXPLORE
        if score < 60:
            return cls.ENGINEER
        if score < 80:
            return cls.OPERATE
        return cls.SCALE

    @property
    def decision(self) -> str:
        return {
            ReadyBand.EXPLORE: "Do not commit to production. Resolve ownership and "
            "architecture gaps first.",
            ReadyBand.ENGINEER: "Build a controlled non-production implementation and "
            "automate the evidence.",
            ReadyBand.OPERATE: "Production candidate, provided every critical dimension "
            "is at least Level 2.",
            ReadyBand.SCALE: "Standardise reusable services and portfolio controls "
            "across workloads.",
        }[self]


# Weights sum to 1.0. Evaluation and Trust carry the most because they are the
# two areas where a confident team is most likely to be wrong and where being
# wrong costs the most.
DIMENSIONS: dict[Dimension, tuple[float, str]] = {
    Dimension.RETRIEVAL: (
        0.15,
        "Corpus authority, chunk and index design, access-control tests, retrieval "
        "quality metrics, citation validation, freshness, retention and deletion.",
    ),
    Dimension.EVALUATION: (
        0.20,
        "Golden and adversarial datasets, deterministic and model graders, SME "
        "calibration, trace and outcome evaluation, release thresholds.",
    ),
    Dimension.ARCHITECTURE: (
        0.15,
        "Boundaries, state, control flow, capacity, resiliency, enumerated failure "
        "modes, tool contracts, rollback and disaster recovery.",
    ),
    Dimension.DATA_GOVERNANCE: (
        0.15,
        "Classification, lineage, residency, consent, retention, deletion, policy "
        "enforcement and authoritative source ownership.",
    ),
    Dimension.YIELD_OPERATIONS: (
        0.15,
        "Service objectives, deployment automation, cost per successful task, support "
        "model, incident response, capacity and value realisation.",
    ),
    Dimension.TRUST: (
        0.20,
        "Security, identity, network controls, monitoring, compliance, Responsible AI, "
        "human oversight and audit.",
    ),
}


class ReadyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DimensionScore(ReadyModel):
    """One dimension's level, and the artifact that justifies it."""

    dimension: Dimension
    level: MaturityLevel
    evidence: str = Field(default="", max_length=1_000)
    gap: str = Field(default="", max_length=1_000)
    owner: str | None = Field(default=None, max_length=128)
    due: date | None = None

    @property
    def weight(self) -> float:
        return DIMENSIONS[self.dimension][0]

    @property
    def weighted_score(self) -> float:
        """Level as a proportion of the maximum, times the dimension weight."""
        return (int(self.level) / int(MaturityLevel.SCALE)) * self.weight * 100.0

    @model_validator(mode="after")
    def _evidence_required_above_explore(self) -> Self:
        # A claim without an artifact scores at the level below. Enforcing it
        # here is what stops the scorecard from measuring optimism.
        if self.level >= MaturityLevel.ENGINEER and not self.evidence.strip():
            raise ValueError(
                f"{self.dimension.value} claims {self.level.name} but cites no evidence; "
                "name the artifact or score one level lower"
            )
        if self.level < MaturityLevel.OPERATE and not self.gap.strip():
            raise ValueError(f"{self.dimension.value} is below Operate and must name its gap")
        return self


class GateResult(ReadyModel):
    """The release decision, and precisely why."""

    passed: bool
    overall_score: float
    band: ReadyBand
    blocking_reasons: tuple[str, ...] = ()
    lowest_critical: Dimension | None = None


class Assessment(ReadyModel):
    """One workload, scored as it is today rather than as it will be next sprint."""

    workload_id: str = Field(min_length=1, max_length=128)
    workload_name: str = Field(min_length=1, max_length=200)
    assessed_by: str = Field(min_length=1, max_length=128)
    assessed_on: date
    risk_tier: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    # High-impact actions justify stricter thresholds, set by the accountable
    # risk owner rather than by the delivery team.
    gate_minimum: float = Field(default=60.0, ge=0.0, le=100.0)
    minimum_critical_level: MaturityLevel = MaturityLevel.ENGINEER
    scores: tuple[DimensionScore, ...]
    notes: str = Field(default="", max_length=2_000)

    @model_validator(mode="after")
    def _every_dimension_scored(self) -> Self:
        scored = {score.dimension for score in self.scores}
        missing = set(DIMENSIONS) - scored
        if missing:
            raise ValueError(
                "assessment is incomplete; missing: " + ", ".join(sorted(d.value for d in missing))
            )
        if len(scored) != len(self.scores):
            raise ValueError("each dimension may be scored only once")
        return self
