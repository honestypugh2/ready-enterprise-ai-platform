"""Audit receipt persistence.

Immutable by convention here and by storage policy in Azure: the Bicep module
provisions the evidence container with immutability enabled, because an audit
record you can quietly edit is not evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from contracts.audit import AuditReceipt


class AuditStore(Protocol):
    async def put(self, receipt: AuditReceipt) -> None: ...
    async def get(self, audit_id: str) -> AuditReceipt | None: ...
    async def get_by_correlation(self, correlation_id: str) -> AuditReceipt | None: ...


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._by_id: dict[str, AuditReceipt] = {}
        self._by_correlation: dict[str, str] = {}

    async def put(self, receipt: AuditReceipt) -> None:
        if receipt.audit_id in self._by_id:
            raise ValueError("audit receipts are immutable once written")
        self._by_id[receipt.audit_id] = receipt
        self._by_correlation[receipt.correlation_id] = receipt.audit_id

    async def get(self, audit_id: str) -> AuditReceipt | None:
        return self._by_id.get(audit_id)

    async def get_by_correlation(self, correlation_id: str) -> AuditReceipt | None:
        audit_id = self._by_correlation.get(correlation_id)
        return self._by_id.get(audit_id) if audit_id else None

    def clear(self) -> None:
        self._by_id.clear()
        self._by_correlation.clear()


class JsonFileAuditStore:
    """Write-once JSON files for the local demo."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, audit_id: str) -> Path:
        if "/" in audit_id or ".." in audit_id:
            raise ValueError("invalid audit id")
        return self._dir / f"{audit_id}.json"

    async def put(self, receipt: AuditReceipt) -> None:
        path = self._path(receipt.audit_id)
        if path.exists():
            raise ValueError("audit receipts are immutable once written")
        path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

    async def get(self, audit_id: str) -> AuditReceipt | None:
        path = self._path(audit_id)
        if not path.is_file():
            return None
        return AuditReceipt.model_validate(json.loads(path.read_text(encoding="utf-8")))

    async def get_by_correlation(self, correlation_id: str) -> AuditReceipt | None:
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            receipt = AuditReceipt.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if receipt.correlation_id == correlation_id:
                return receipt
        return None
