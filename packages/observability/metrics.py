"""Quality, action and cost metrics.

Uptime is not quality. These are the counters that answer "is the system
right?" rather than "is the system up?", and they are recorded in the same
place as latency so a single view can show both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from contracts.action import ActionStatus
from contracts.approval import ApprovalState
from contracts.policy import Disposition


@dataclass(slots=True)
class WorkloadMetrics:
    """In-process counters.

    Deliberately simple. In Azure mode the same values are emitted as
    OpenTelemetry metrics and Application Insights custom metrics; this
    structure is what the local demo and the tests read.
    """

    tasks_started: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0

    predictions: int = 0
    low_confidence_predictions: int = 0
    detector_failures: int = 0

    retrievals: int = 0
    empty_retrievals: int = 0
    stale_evidence_hits: int = 0
    injection_signals: int = 0

    recommendations: int = 0
    ungrounded_refusals: int = 0

    policy_denials: int = 0
    approvals_requested: int = 0
    approvals_rejected: int = 0
    human_corrections: int = 0

    writes_succeeded: int = 0
    writes_dry_run: int = 0
    writes_duplicate_suppressed: int = 0
    writes_failed: int = 0

    unauthorized_attempts: int = 0

    latency_ms_by_step: dict[str, list[float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record_step_latency(self, step: str, latency_ms: float) -> None:
        with self._lock:
            self.latency_ms_by_step.setdefault(step, []).append(latency_ms)

    def record_disposition(self, disposition: Disposition) -> None:
        if disposition is Disposition.NO_ACTION:
            self.policy_denials += 1

    def record_approval_state(self, state: ApprovalState) -> None:
        if state is ApprovalState.PENDING:
            self.approvals_requested += 1
        elif state is ApprovalState.REJECTED:
            self.approvals_rejected += 1
            self.human_corrections += 1
        elif state is ApprovalState.MODIFIED:
            self.human_corrections += 1

    def record_action(self, status: ActionStatus) -> None:
        match status:
            case ActionStatus.SUCCEEDED:
                self.writes_succeeded += 1
            case ActionStatus.DRY_RUN:
                self.writes_dry_run += 1
            case ActionStatus.DUPLICATE_SUPPRESSED:
                self.writes_duplicate_suppressed += 1
            case ActionStatus.FAILED:
                self.writes_failed += 1
            case _:
                pass

    @property
    def correction_rate(self) -> float | None:
        """How often a human changed or reversed a proposal.

        The most informative operational metric on this platform, because it
        tracks trust rather than availability. ``None`` until at least one
        approval has been requested, since a rate over zero samples is noise.
        """
        if self.approvals_requested == 0:
            return None
        return self.human_corrections / self.approvals_requested

    def percentile(self, step: str, quantile: float) -> float | None:
        """Nearest-rank percentile over locally observed latencies.

        These are demonstration measurements from this process only. They are
        not a capacity claim and must not be presented as one.
        """
        if not 0.0 < quantile <= 1.0:
            raise ValueError("quantile must be in (0, 1]")
        samples = sorted(self.latency_ms_by_step.get(step, []))
        if not samples:
            return None
        index = max(0, min(len(samples) - 1, round(quantile * len(samples)) - 1))
        return samples[index]

    def snapshot(self) -> dict[str, float | int | None]:
        return {
            "tasks_started": self.tasks_started,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "predictions": self.predictions,
            "low_confidence_predictions": self.low_confidence_predictions,
            "detector_failures": self.detector_failures,
            "empty_retrievals": self.empty_retrievals,
            "stale_evidence_hits": self.stale_evidence_hits,
            "injection_signals": self.injection_signals,
            "ungrounded_refusals": self.ungrounded_refusals,
            "policy_denials": self.policy_denials,
            "approvals_requested": self.approvals_requested,
            "approvals_rejected": self.approvals_rejected,
            "writes_succeeded": self.writes_succeeded,
            "writes_dry_run": self.writes_dry_run,
            "writes_duplicate_suppressed": self.writes_duplicate_suppressed,
            "writes_failed": self.writes_failed,
            "unauthorized_attempts": self.unauthorized_attempts,
            "correction_rate": self.correction_rate,
        }


METRICS = WorkloadMetrics()
