"""Workload identity resolution.

Every component authenticates as itself. There is no shared service principal,
no secret in configuration, and no code path in this repository that accepts a
connection string. Local mode uses no credential at all, which is what makes
the quickstart honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from platform_config import ExecutionMode, PlatformSettings

AZURE_MANAGEMENT_SCOPE = "https://management.azure.com/.default"


class WorkloadIdentity(StrEnum):
    """The distinct identities the platform runs under.

    Separate identities exist so an audit log can attribute an action to a
    component rather than to "the platform", and so a compromise of the
    reasoning path inherits permissions that cannot write anything.
    """

    API = "reap-api"
    WORKER = "reap-worker"
    DETECTOR_CLIENT = "reap-detector-client"
    RETRIEVAL_CLIENT = "reap-retrieval-client"
    REASONING_CLIENT = "reap-reasoning-client"
    SCOPED_WRITER = "reap-scoped-writer"


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """The principal on whose behalf work is being done.

    Built from a validated access token at the API boundary. It is never
    constructed from model output and never from a request body.
    """

    principal_id: str
    display_name: str
    roles: frozenset[str]
    entitlement_groups: frozenset[str]
    tenant_id: str = "demo-tenant"

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @classmethod
    def local_demo_operator(cls) -> IdentityContext:
        """Synthetic identity for local mode. Not a real person, by design."""
        return cls(
            principal_id="synthetic-operator-001",
            display_name="Demo Line Operator",
            roles=frozenset({"line_operator"}),
            entitlement_groups=frozenset({"grp-manufacturing-all", "grp-line-demo-l1"}),
        )

    @classmethod
    def local_demo_approver(cls, role: str = "maintenance_lead") -> IdentityContext:
        return cls(
            principal_id=f"synthetic-approver-{role}",
            display_name=f"Demo {role.replace('_', ' ').title()}",
            roles=frozenset({role}),
            entitlement_groups=frozenset(
                {"grp-manufacturing-all", "grp-line-demo-l1", "grp-maintenance-standards"}
            ),
        )


def resolve_credential(settings: PlatformSettings, *, identity: WorkloadIdentity) -> Any | None:
    """Return a managed-identity credential, or ``None`` in local mode.

    ``azure-identity`` is an optional extra, so its absence is a configuration
    error with a clear message rather than an import traceback at request time.
    """
    if settings.mode is ExecutionMode.LOCAL_MOCK:
        return None

    try:
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415  (optional extra)
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            f"{identity.value} requires a credential; run `uv sync --extra azure`"
        ) from exc

    # DefaultAzureCredential resolves to the user-assigned managed identity in
    # Azure and to the developer's own signed-in identity locally. Neither path
    # involves a stored secret.
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)
