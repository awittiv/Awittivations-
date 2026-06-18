"""
Routes: hitl.py
Human-in-the-Loop review endpoints for the Runtime Authorization Gate.

Admin operators use these endpoints to approve or reject sweeps that were
held by hitl_gate.route_sweep() due to high value or W2G reporting thresholds.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any

from auth_admin import get_admin_user_id as get_admin_operator_id
from services.hitl_gate import approve_sweep, reject_sweep, get_pending_queue

router = APIRouter(prefix="/hitl", tags=["HITL"])


class ApproveRequest(BaseModel):
    justification_code: str
    modifications: dict[str, Any] | None = None


class RejectRequest(BaseModel):
    reason: str


@router.get("/queue")
async def list_pending_queue(operator_id: str = Depends(get_admin_operator_id)):
    """List all sweeps currently pending human review, oldest first."""
    return await get_pending_queue()


@router.post("/approve/{task_id}")
async def approve(
    task_id: str,
    body: ApproveRequest,
    operator_id: str = Depends(get_admin_operator_id),
):
    """
    Approve a queued sweep and release it for execution.
    Optionally pass modifications.gross_amount to correct the amount before execution.
    """
    try:
        result = await approve_sweep(
            task_id=task_id,
            operator_id=operator_id,
            justification_code=body.justification_code,
            modifications=body.modifications,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return result


@router.post("/reject/{task_id}")
async def reject(
    task_id: str,
    body: RejectRequest,
    operator_id: str = Depends(get_admin_operator_id),
):
    """Reject a queued sweep. No execution occurs."""
    try:
        return await reject_sweep(
            task_id=task_id,
            operator_id=operator_id,
            reason=body.reason,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
