"""Shared dependencies.

The platform assembly is built once at start-up. Building it per request would
re-read policy and re-resolve credentials on every call, and would make the
policy version served by two concurrent requests potentially different.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from platform_config import PlatformSettings, get_settings
from security.identity import IdentityContext
from workflows import PlatformAssembly


def get_assembly(request: Request) -> PlatformAssembly:
    assembly = getattr(request.app.state, "assembly", None)
    if not isinstance(assembly, PlatformAssembly):  # pragma: no cover - lifespan guarantees this
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="platform is not initialised",
        )
    return assembly


def get_correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "corr_unknown"))


def get_identity(
    x_demo_role: Annotated[str | None, Header(alias="x-demo-role")] = None,
) -> IdentityContext:
    """Resolve the calling principal.

    In local mode this returns a synthetic identity selected by a header, which
    is what lets the entitlement demonstration show two users getting different
    answers from one index. **This is not authentication.** In Azure and
    production modes the identity is built from a validated Entra token at the
    gateway, and this dependency is replaced — see
    ``docs/security/authorization-model.md``.
    """
    if x_demo_role in {None, "", "line_operator"}:
        return IdentityContext.local_demo_operator()
    return IdentityContext.local_demo_approver(str(x_demo_role))


AssemblyDep = Annotated[PlatformAssembly, Depends(get_assembly)]
SettingsDep = Annotated[PlatformSettings, Depends(get_settings)]
IdentityDep = Annotated[IdentityContext, Depends(get_identity)]
CorrelationDep = Annotated[str, Depends(get_correlation_id)]
