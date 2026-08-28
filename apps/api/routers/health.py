"""Liveness, readiness and health.

Three separate endpoints because they answer three different questions, and
collapsing them is how a pod gets restarted for a dependency outage it could
have ridden out.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from api.dependencies import AssemblyDep, SettingsDep
from api.schemas import HealthResponse

router = APIRouter(tags=["operations"])


@router.get("/livez", summary="Liveness: is the process running?")
async def livez() -> dict[str, str]:
    """Never touches a dependency. A failing dependency must not restart the pod."""
    return {"status": "alive"}


@router.get("/readyz", summary="Readiness: can this replica serve traffic?")
async def readyz(assembly: AssemblyDep, response: Response) -> dict[str, object]:
    planes = await assembly.health()
    ready = all(planes.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "degraded", "planes": planes}


@router.get("/healthz", response_model=HealthResponse, summary="Detailed health and governance")
async def healthz(assembly: AssemblyDep, settings: SettingsDep) -> HealthResponse:
    planes = await assembly.health()
    return HealthResponse(
        status="ok" if all(planes.values()) else "degraded",
        mode=settings.mode.value,
        planes=planes,
        policy_version=f"{assembly.policy.version} ({assembly.policy.sha[:18]})",
        routing_policy_version=f"{assembly.router.version} ({assembly.router.sha[:18]})",
        kill_switch_engaged=settings.governance.kill_switch_engaged,
        dry_run=settings.connector.dry_run,
    )
