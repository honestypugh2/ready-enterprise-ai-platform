"""Approval persistence.

Two implementations: in-memory for tests, and a JSON-file store so a local demo
survives an API restart without introducing a database dependency into the
quickstart. Neither is a production store; see IMPLEMENTATION_STATUS.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from contracts.approval import ApprovalRecord, ApprovalState


class ApprovalStore(Protocol):
    async def put(self, record: ApprovalRecord) -> None: ...
    async def get(self, approval_id: str) -> ApprovalRecord | None: ...
    async def list_by_state(self, state: ApprovalState) -> tuple[ApprovalRecord, ...]: ...


class InMemoryApprovalStore:
    """Process-local store. Deterministic and empty at every test start."""

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    async def put(self, record: ApprovalRecord) -> None:
        self._records[record.approval_id] = record

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    async def list_by_state(self, state: ApprovalState) -> tuple[ApprovalRecord, ...]:
        return tuple(r for r in self._records.values() if r.state is state)

    def clear(self) -> None:
        self._records.clear()


class JsonFileApprovalStore:
    """Append-safe JSON store for the local demo. One file per approval."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, approval_id: str) -> Path:
        # Approval ids are constrained by the contract pattern, so no traversal
        # is reachable here; the check is kept as a defence-in-depth assertion.
        if "/" in approval_id or ".." in approval_id:
            raise ValueError("invalid approval id")
        return self._dir / f"{approval_id}.json"

    async def put(self, record: ApprovalRecord) -> None:
        self._path(record.approval_id).write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        path = self._path(approval_id)
        if not path.is_file():
            return None
        return ApprovalRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    async def list_by_state(self, state: ApprovalState) -> tuple[ApprovalRecord, ...]:
        records: list[ApprovalRecord] = []
        for path in sorted(self._dir.glob("*.json")):
            record = ApprovalRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if record.state is state:
                records.append(record)
        return tuple(records)
