"""In-memory enterprise system mocks.

Three shapes — ERP work orders, ServiceNow incidents, Dynamics 365 cases —
because the interesting differences between them are the payload contract and
the reference format, and a demo that only ever writes to one target hides the
adapter boundary the architecture depends on.

Nothing here reaches a network. Failure injection is first class so the
resilience tests and the demo failure path exercise the same code.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from connectors.base import ConnectorError, DuplicateWriteError
from contracts.action import ActionKind, ActionRequest


@dataclass(slots=True)
class _Record:
    external_reference: str
    idempotency_key: str
    payload: dict[str, str]
    compensated: bool = False


@dataclass(slots=True)
class MockConnectorState:
    """Shared bookkeeping so tests can assert on what was and was not written."""

    records: dict[str, _Record] = field(default_factory=dict)
    by_key: dict[str, str] = field(default_factory=dict)
    call_count: int = 0

    def clear(self) -> None:
        self.records.clear()
        self.by_key.clear()
        self.call_count = 0


class MockEnterpriseConnector:
    """Deterministic stand-in for a system of record."""

    def __init__(
        self,
        *,
        system_name: str,
        reference_prefix: str,
        supported_actions: frozenset[ActionKind],
        latency_ms: float = 12.0,
        fail_times: int = 0,
        fail_permanently: bool = False,
        healthy_flag: bool = True,
    ) -> None:
        self.system_name = system_name
        self.supported_actions = supported_actions
        self.state = MockConnectorState()
        self._prefix = reference_prefix
        self._latency_ms = latency_ms
        self._fail_times = fail_times
        self._fail_permanently = fail_permanently
        self._healthy = healthy_flag

    async def healthy(self) -> bool:
        return self._healthy

    async def find_by_idempotency_key(self, key: str) -> str | None:
        return self.state.by_key.get(key)

    async def execute(self, request: ActionRequest) -> str:
        if request.kind not in self.supported_actions:
            raise ConnectorError(f"{self.system_name} does not support action {request.kind.value}")

        existing = self.state.by_key.get(request.idempotency_key)
        if existing is not None:
            raise DuplicateWriteError(
                f"idempotency key already applied as {existing}",
                correlation_id=request.correlation_id,
            )

        self.state.call_count += 1
        await asyncio.sleep(self._latency_ms / 1000.0)

        if self._fail_permanently:
            raise ConnectorError(
                f"{self.system_name} is unavailable", correlation_id=request.correlation_id
            )
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectorError(
                f"{self.system_name} transient failure", correlation_id=request.correlation_id
            )

        reference = f"{self._prefix}-{len(self.state.records) + 1:06d}"
        self.state.records[reference] = _Record(
            external_reference=reference,
            idempotency_key=request.idempotency_key,
            payload=request.payload_dict(),
        )
        self.state.by_key[request.idempotency_key] = reference
        return reference

    async def compensate(self, external_reference: str, *, reason: str) -> str:
        record = self.state.records.get(external_reference)
        if record is None:
            raise ConnectorError(f"unknown reference {external_reference}")
        record.compensated = True
        record.payload["compensation_reason"] = reason
        return f"{external_reference}-REV"


def mock_erp() -> MockEnterpriseConnector:
    """ERP work-order surface (Dynamics 365 Supply Chain-shaped)."""
    return MockEnterpriseConnector(
        system_name="mock-erp",
        reference_prefix="WO",
        supported_actions=frozenset(
            {
                ActionKind.CREATE_WORK_ORDER,
                ActionKind.QUARANTINE_BATCH,
                ActionKind.SCHEDULE_INSPECTION,
                ActionKind.NOTIFY_SUPERVISOR,
            }
        ),
    )


def mock_servicenow() -> MockEnterpriseConnector:
    """IT/OT service management surface."""
    return MockEnterpriseConnector(
        system_name="mock-servicenow",
        reference_prefix="INC",
        supported_actions=frozenset({ActionKind.CREATE_INCIDENT, ActionKind.NOTIFY_SUPERVISOR}),
    )


def mock_dynamics365() -> MockEnterpriseConnector:
    """Customer-facing case surface."""
    return MockEnterpriseConnector(
        system_name="mock-d365",
        reference_prefix="CASE",
        supported_actions=frozenset(
            {
                ActionKind.CREATE_INCIDENT,
                ActionKind.CREATE_WORK_ORDER,
                ActionKind.NOTIFY_SUPERVISOR,
            }
        ),
    )
