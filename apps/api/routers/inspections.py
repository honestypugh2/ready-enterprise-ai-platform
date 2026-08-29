"""Inspection endpoints.

``POST /v1/inspections`` runs steps 1-8 and stops at the approval gate when
policy requires one. Completion is a **separate** call after a decision, because
the write happening in a different request from the proposal is exactly the
boundary an approval exists to create.
"""

from __future__ import annotations

from collections import OrderedDict

from fastapi import APIRouter, HTTPException, status

from api.dependencies import AssemblyDep, CorrelationDep, IdentityDep, SettingsDep
from api.schemas import InspectionRequest, InspectionResponse, ScenarioRequest
from api.views import inspection_response
from cli.scenarios import get_scenario
from contracts.common import CorrelationContext
from contracts.detection import DetectionRequest

router = APIRouter(prefix="/v1/inspections", tags=["inspection"])

# Outcomes are kept per replica so the approval flow can resume. A production
# deployment replaces this with the evidence store; see IMPLEMENTATION_STATUS.md.
#
# Bounded, because an unbounded cache in a request path is a memory leak that
# presents as a replica dying under sustained traffic. Eviction loses a pending
# approval, which is the same failure a restart already causes — the durable
# store is the real fix.
_MAX_RETAINED_OUTCOMES = 1_000
_OUTCOMES: OrderedDict[str, object] = OrderedDict()


def remember(correlation_id: str, outcome: object) -> None:
    """Store a transaction so a later approval decision can resume it."""
    _OUTCOMES[correlation_id] = outcome
    _OUTCOMES.move_to_end(correlation_id)
    while len(_OUTCOMES) > _MAX_RETAINED_OUTCOMES:
        _OUTCOMES.popitem(last=False)


def recall(correlation_id: str) -> object | None:
    outcome = _OUTCOMES.get(correlation_id)
    if outcome is not None:
        _OUTCOMES.move_to_end(correlation_id)
    return outcome


@router.post(
    "",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a frame for governed inspection",
)
async def create_inspection(
    payload: InspectionRequest,
    assembly: AssemblyDep,
    identity: IdentityDep,
    settings: SettingsDep,
    correlation_id: CorrelationDep,
) -> InspectionResponse:
    request = DetectionRequest(
        line_id=payload.line_id,
        station_id=payload.station_id,
        product_sku=payload.product_sku,
        batch_id=payload.batch_id,
        frame_hash=payload.frame_hash,
        frame_uri=payload.frame_uri,
        classification=payload.classification,
    )
    outcome = await assembly.workflow.run(
        request,
        identity=identity,
        context=CorrelationContext(
            correlation_id=correlation_id, initiated_by=identity.principal_id
        ),
        batch_defect_count=payload.batch_defect_count,
    )
    remember(outcome.correlation_id, outcome)
    return inspection_response(outcome, mode=settings.mode.value)


@router.post(
    "/scenario",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run a pinned demonstration scenario",
)
async def run_scenario(
    payload: ScenarioRequest,
    assembly: AssemblyDep,
    identity: IdentityDep,
    settings: SettingsDep,
    correlation_id: CorrelationDep,
) -> InspectionResponse:
    try:
        scenario = get_scenario(payload.scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    outcome = await assembly.workflow.run(
        scenario.to_request(),
        identity=identity,
        context=CorrelationContext(
            correlation_id=correlation_id, initiated_by=identity.principal_id
        ),
        batch_defect_count=scenario.batch_defect_count,
    )
    remember(outcome.correlation_id, outcome)
    return inspection_response(outcome, mode=settings.mode.value)


@router.get(
    "/{correlation_id}",
    response_model=InspectionResponse,
    summary="Retrieve a transaction by correlation id",
)
async def get_inspection(correlation_id: str, settings: SettingsDep) -> InspectionResponse:
    outcome = recall(correlation_id)
    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown correlation id")
    return inspection_response(outcome, mode=settings.mode.value)  # type: ignore[arg-type]
