"""Approval endpoints.

The decision and the write are separate operations on separate resources. That
separation is the control: an approval is a decision about a fingerprinted
proposal, and the write is a later action that re-verifies the binding.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import AssemblyDep, SettingsDep
from api.routers.inspections import recall, remember
from api.schemas import ApprovalDecisionRequest, ApprovalView, InspectionResponse
from api.views import approval_view, inspection_response
from contracts.approval import ApprovalDecision, ApprovalState
from contracts.errors import ApprovalRequiredError
from workflows import WorkflowOutcome

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


@router.get("", summary="List approvals awaiting a decision")
async def list_pending(assembly: AssemblyDep) -> list[dict[str, object]]:
    records = await assembly.approvals.list_pending()
    return [
        {
            "approval_id": record.approval_id,
            "correlation_id": record.correlation_id,
            "required_role": record.request.required_role,
            "dual_control_required": record.request.dual_control_required,
            "expires_at": record.request.expires_at.isoformat(),
            "proposed_action_summary": record.request.proposed_action_summary,
            "decisions_recorded": len(record.decisions),
        }
        for record in records
    ]


@router.get("/{approval_id}", response_model=ApprovalView, summary="Retrieve one approval")
async def get_approval(approval_id: str, assembly: AssemblyDep) -> ApprovalView:
    record = await assembly.approvals.get(approval_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown approval")
    view = approval_view(WorkflowOutcome(correlation_id=record.correlation_id, approval=record))
    assert view is not None
    return view


@router.post(
    "/{approval_id}/decision",
    response_model=InspectionResponse,
    summary="Record a decision and, when permitted, complete the transaction",
)
async def decide(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    assembly: AssemblyDep,
    settings: SettingsDep,
) -> InspectionResponse:
    record = await assembly.approvals.get(approval_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown approval")

    try:
        record = await assembly.approvals.decide(
            approval_id,
            ApprovalDecision(
                approver_principal_id=payload.approver_principal_id,
                approver_role=payload.approver_role,
                state=ApprovalState(payload.decision),
                rationale=payload.rationale,
                modified_payload=tuple(sorted(payload.modified_payload.items())),
            ),
        )
    except ApprovalRequiredError as exc:
        # Separation of duties and role mismatches are 403, not 500: the caller
        # is authenticated but not permitted to make this particular decision.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    outcome = recall(record.correlation_id)
    if not isinstance(outcome, WorkflowOutcome):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the originating transaction is not available on this replica",
        )

    outcome.approval = record
    if record.state.permits_write:
        outcome = await assembly.workflow.complete(outcome, dry_run=settings.connector.dry_run)
    remember(outcome.correlation_id, outcome)
    return inspection_response(outcome, mode=settings.mode.value)
