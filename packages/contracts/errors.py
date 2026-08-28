"""Typed failures.

Each error names the plane that refused and whether the refusal is safe to
retry. A caller that cannot tell a policy denial from a timeout will eventually
retry a denial, which is how "the model kept trying until it got through"
incidents start.
"""

from __future__ import annotations


class PlatformError(Exception):
    """Base class. ``retryable`` is part of the contract, not an implementation detail."""

    retryable: bool = False
    plane: str = "platform"

    def __init__(self, message: str, *, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id

    def __str__(self) -> str:
        if self.correlation_id:
            return f"{self.message} (correlation_id={self.correlation_id})"
        return self.message


class ContractViolationError(PlatformError):
    """A payload crossing a plane boundary failed schema validation."""

    plane = "contracts"


class PolicyDeniedError(PlatformError):
    """Deterministic policy refused the action. Never retryable by design."""

    plane = "policy"


class ApprovalRequiredError(PlatformError):
    """A consequential action was attempted without a bound approval record."""

    plane = "approvals"


class KillSwitchEngagedError(PlatformError):
    """The workload is administratively disabled."""

    plane = "operations"


class UpstreamUnavailableError(PlatformError):
    """A dependency timed out or failed. Retryable under the caller's budget."""

    retryable = True
    plane = "integration"


class BudgetExceededError(PlatformError):
    """A cost or step budget was exhausted before the work completed."""

    plane = "cost"


class UnauthorizedWriteError(PlatformError):
    """Something other than the sole scoped writer attempted a mutation."""

    plane = "security"
