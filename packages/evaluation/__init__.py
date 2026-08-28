"""Evaluation plane.

Evaluation is the specification, not a report produced after the fact. If
nobody can state the dataset and the threshold that would block a release, the
workload has no acceptance criteria and the release decision is an opinion.

Six things are graded, matching the workflow's own steps: the predictive
signal, retrieval quality, groundedness and citation precision, tool and action
correctness, policy compliance and safety, and the business outcome. A workload
that grades only the final natural-language answer can score well while
retrieving the wrong evidence and taking the wrong action.

Two properties this harness holds itself to:

* **A broken grader is a failure, not a missing value.** If a grader cannot
  run, the case scores zero and the run fails. A release that proceeds because
  the evaluator was broken is exactly what the gate exists to prevent.
* **Model graders must be calibrated before they gate anything.** A model
  grader that has never been compared against human labels for this corpus
  produces numbers with unknown meaning.
"""

from evaluation.graders import (
    ActionCorrectnessGrader,
    CitationPrecisionGrader,
    EntitlementGrader,
    Grader,
    GradeResult,
    GroundednessGrader,
    PolicyComplianceGrader,
    RefusalGrader,
    RetrievalRelevanceGrader,
    SafetyGrader,
)
from evaluation.harness import EvaluationHarness, EvaluationReport
from evaluation.models import CaseKind, EvalCase, EvalDataset, SystemOutput, load_dataset
from evaluation.runner import WorkflowEvaluationRunner, frame_hash_for
from evaluation.suite import DEFAULT_DATASET_PATH, default_graders, run_release_gate

__all__ = [
    "DEFAULT_DATASET_PATH",
    "ActionCorrectnessGrader",
    "CaseKind",
    "CitationPrecisionGrader",
    "EntitlementGrader",
    "EvalCase",
    "EvalDataset",
    "EvaluationHarness",
    "EvaluationReport",
    "GradeResult",
    "Grader",
    "GroundednessGrader",
    "PolicyComplianceGrader",
    "RefusalGrader",
    "RetrievalRelevanceGrader",
    "SafetyGrader",
    "SystemOutput",
    "WorkflowEvaluationRunner",
    "default_graders",
    "frame_hash_for",
    "load_dataset",
    "run_release_gate",
]
