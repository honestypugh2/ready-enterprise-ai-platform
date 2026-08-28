"""Human oversight plane.

Approval sits in front of high-impact, irreversible, regulated or financially
material actions, and nowhere else — approval on low-impact actions trains
people to click through the ones that matter.

The approver is shown evidence, the proposed action, the authoritative values,
the policy result and the expected downstream effect. A natural-language
summary on its own is not an approval surface, so ``ApprovalEvidence`` carries
those five things as data.
"""

from approvals.service import ApprovalService
from approvals.state_machine import InvalidTransitionError, assert_transition, can_transition
from approvals.store import ApprovalStore, InMemoryApprovalStore, JsonFileApprovalStore

__all__ = [
    "ApprovalService",
    "ApprovalStore",
    "InMemoryApprovalStore",
    "InvalidTransitionError",
    "JsonFileApprovalStore",
    "assert_transition",
    "can_transition",
]
