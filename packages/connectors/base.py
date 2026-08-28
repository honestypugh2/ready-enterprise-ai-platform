"""Enterprise system adapter protocol.

An adapter knows how to talk to one system of record. It does not know about
approvals, policy or idempotency — those are the writer's job, and keeping them
out of the adapter is what stops each new integration from re-implementing (and
re-weakening) the controls.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contracts.action import ActionKind, ActionRequest
from contracts.errors import UpstreamUnavailableError


class ConnectorError(UpstreamUnavailableError):
    plane = "connectors"


class DuplicateWriteError(ConnectorError):
    """The idempotency key has already been applied. Not an error condition."""

    retryable = False


@runtime_checkable
class EnterpriseConnector(Protocol):
    """One system of record."""

    system_name: str
    supported_actions: frozenset[ActionKind]

    async def find_by_idempotency_key(self, key: str) -> str | None:
        """Return the existing external reference for this key, if any."""
        ...

    async def execute(self, request: ActionRequest) -> str:
        """Perform the mutation and return the external reference."""
        ...

    async def compensate(self, external_reference: str, *, reason: str) -> str:
        """Reverse a previously applied mutation and return the compensation reference."""
        ...

    async def healthy(self) -> bool: ...
