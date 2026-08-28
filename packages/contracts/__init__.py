"""Versioned contracts shared by every plane of the platform.

Contracts are the only thing planes are allowed to know about each other. A
plane may depend on ``contracts``; it may not import another plane's internals.
That rule is what makes each plane independently reviewable, testable and
replaceable, and it is enforced by ``tests/contract/test_plane_boundaries.py``.
"""

from contracts.action import ActionKind, ActionReceipt, ActionRequest, ActionStatus
from contracts.approval import ApprovalDecision, ApprovalRecord, ApprovalRequest, ApprovalState
from contracts.audit import AuditReceipt, AuditStep
from contracts.common import (
    CONTRACT_VERSION,
    Classification,
    CorrelationContext,
    CostCategory,
    ExecutionLocation,
    Provenance,
    new_id,
    utcnow,
)
from contracts.detection import DetectionRequest, DetectionResult, DetectionSeverity, Prediction
from contracts.errors import (
    ApprovalRequiredError,
    ContractViolationError,
    KillSwitchEngagedError,
    PlatformError,
    PolicyDeniedError,
    UpstreamUnavailableError,
)
from contracts.events import EventEnvelope, EventType
from contracts.policy import Disposition, PolicyDecision, PolicyObligation
from contracts.reasoning import Citation, ReasoningRequest, Recommendation
from contracts.retrieval import RetrievalQuery, RetrievalResult, RetrievalStrategy, RetrievedItem
from contracts.routing import RouteCandidate, RouteDecision, RouteKind, RouteRequest, TaskType
from contracts.taxonomy import (
    DEFECT_LABELS,
    DEFECT_TAXONOMY,
    NO_DEFECT_LABEL,
    DefectClass,
    is_safety_relevant,
    severity_for,
)

__all__ = [
    "CONTRACT_VERSION",
    "DEFECT_LABELS",
    "DEFECT_TAXONOMY",
    "NO_DEFECT_LABEL",
    "ActionKind",
    "ActionReceipt",
    "ActionRequest",
    "ActionStatus",
    "ApprovalDecision",
    "ApprovalRecord",
    "ApprovalRequest",
    "ApprovalRequiredError",
    "ApprovalState",
    "AuditReceipt",
    "AuditStep",
    "Citation",
    "Classification",
    "ContractViolationError",
    "CorrelationContext",
    "CostCategory",
    "DefectClass",
    "DetectionRequest",
    "DetectionResult",
    "DetectionSeverity",
    "Disposition",
    "EventEnvelope",
    "EventType",
    "ExecutionLocation",
    "KillSwitchEngagedError",
    "PlatformError",
    "PolicyDecision",
    "PolicyDeniedError",
    "PolicyObligation",
    "Prediction",
    "Provenance",
    "ReasoningRequest",
    "Recommendation",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalStrategy",
    "RetrievedItem",
    "RouteCandidate",
    "RouteDecision",
    "RouteKind",
    "RouteRequest",
    "TaskType",
    "UpstreamUnavailableError",
    "is_safety_relevant",
    "new_id",
    "severity_for",
    "utcnow",
]
