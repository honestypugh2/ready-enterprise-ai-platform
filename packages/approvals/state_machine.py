"""Approval state machine.

Transitions are explicit and total. An approval that "just ends up approved"
because a code path forgot a check is the failure this table exists to prevent.
"""

from __future__ import annotations

from contracts.approval import ApprovalState

# Only these transitions exist. Everything else is rejected with the state pair
# named in the error, so an invalid transition is diagnosable from the log line.
_ALLOWED: dict[ApprovalState, frozenset[ApprovalState]] = {
    ApprovalState.NOT_REQUIRED: frozenset(),
    ApprovalState.PENDING: frozenset(
        {
            # Self-transition: under dual control the first verdict is recorded
            # but the approval stays open until a second distinct principal
            # decides. MODIFIED means the payload changed, not "half approved".
            ApprovalState.PENDING,
            ApprovalState.APPROVED,
            ApprovalState.REJECTED,
            ApprovalState.MODIFIED,
            ApprovalState.EXPIRED,
            ApprovalState.REVOKED,
            ApprovalState.FAILED,
        }
    ),
    # A modified approval is still open: the modification must itself be
    # confirmed before it permits a write under dual control.
    ApprovalState.MODIFIED: frozenset(
        {
            ApprovalState.APPROVED,
            ApprovalState.REJECTED,
            ApprovalState.EXPIRED,
            ApprovalState.REVOKED,
        }
    ),
    ApprovalState.APPROVED: frozenset({ApprovalState.REVOKED}),
    ApprovalState.REJECTED: frozenset(),
    ApprovalState.EXPIRED: frozenset(),
    ApprovalState.REVOKED: frozenset(),
    ApprovalState.FAILED: frozenset(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, current: ApprovalState, target: ApprovalState) -> None:
        super().__init__(f"cannot transition approval from {current.value} to {target.value}")
        self.current = current
        self.target = target


def can_transition(current: ApprovalState, target: ApprovalState) -> bool:
    return target in _ALLOWED[current]


def assert_transition(current: ApprovalState, target: ApprovalState) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
