"""
Service: hitl_gate.py
Runtime Authorization Gate for Atomic Sweeps — Michigan Bulletin 2026-03-BT.

Sweeps above HIGH_VALUE_THRESHOLD or flagged W2G-reportable are held in the
hitl_review_queue table pending human operator sign-off. Low-risk sweeps
pass through autonomously.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from services import supabase_service

logger = logging.getLogger("HARF.SweepGate")

HIGH_VALUE_THRESHOLD = 500.00  # USD — sweeps at or above this need human review

VALID_JUSTIFICATION_CODES = [
    "ROUTINE_VERIFIED",
    "LARGE_SWEEP_APPROVED",
    "W2G_CONFIRMED",
    "DATA_CORRECTION",
    "OVERRIDE_APPROVED",
]


def _requires_review(gross_amount: float, w2g_reportable: bool) -> tuple[bool, str]:
    if w2g_reportable:
        return True, "W2G_THRESHOLD_TRIGGERED"
    if gross_amount >= HIGH_VALUE_THRESHOLD:
        return True, "HIGH_VALUE_SWEEP"
    return False, ""


async def route_sweep(
    merchant_id: str,
    merchant_wallet: str | None,
    gross_amount: float,
    source: str,
    reference_id: str | None,
    sweep_breakdown: dict,
) -> dict:
    """
    Entry point called by the payments route.
    Returns either a PENDING response (queued for review) or executes immediately.
    """
    needs_review, reason = _requires_review(gross_amount, sweep_breakdown.get("w2g_reportable", False))

    if not needs_review:
        from services.sweep_engine import execute_atomic_sweep
        return await execute_atomic_sweep(
            merchant_id=merchant_id,
            merchant_wallet=merchant_wallet,
            gross_amount=gross_amount,
            source=source,
            reference_id=reference_id,
        )

    client = supabase_service.get_client()
    result = client.table("hitl_review_queue").insert({
        "merchant_id": merchant_id,
        "gross_amount": gross_amount,
        "source": source,
        "reference_id": reference_id,
        "trigger_reason": reason,
        "sweep_breakdown": sweep_breakdown,
        "status": "pending",
    }).execute()

    task_id = result.data[0]["task_id"]
    logger.warning(
        f"HITL GATE: Sweep queued — task={task_id}, reason={reason}, amount=${gross_amount:.2f}"
    )

    return {
        "status": "PENDING_HUMAN_REVIEW",
        "task_id": task_id,
        "trigger_reason": reason,
        "sweep_breakdown": sweep_breakdown,
        "message": f"Sweep of ${gross_amount:.2f} requires human authorization. Review at POST /hitl/approve.",
    }


async def approve_sweep(
    task_id: str,
    operator_id: str,
    justification_code: str,
    modifications: dict | None = None,
) -> dict:
    """
    Human operator releases a queued sweep for execution.
    Optionally applies amount corrections before execution.
    """
    if justification_code not in VALID_JUSTIFICATION_CODES:
        raise ValueError(
            f"Invalid justification code. Must be one of: {VALID_JUSTIFICATION_CODES}"
        )

    client = supabase_service.get_client()
    row = (
        client.table("hitl_review_queue")
        .select("*")
        .eq("task_id", task_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if not row.data:
        raise KeyError(f"Task {task_id} not found or already resolved.")

    task = row.data[0]
    final_amount = float(
        modifications.get("gross_amount", task["gross_amount"]) if modifications else task["gross_amount"]
    )

    if final_amount <= 0:
        raise ValueError(f"Modified gross_amount must be positive, got {final_amount}")

    client.table("hitl_review_queue").update({
        "status": "approved",
        "operator_id": operator_id,
        "justification_code": justification_code,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "operator_notes": modifications or {},
    }).eq("task_id", task_id).execute()

    logger.info(f"HITL APPROVE: task={task_id}, operator={operator_id}, code={justification_code}")

    from services.sweep_engine import execute_atomic_sweep
    from services.supabase_service import get_merchant_by_id

    merchant = await get_merchant_by_id(task["merchant_id"])
    result = await execute_atomic_sweep(
        merchant_id=task["merchant_id"],
        merchant_wallet=merchant.get("wallet_address") if merchant else None,
        gross_amount=final_amount,
        source=task["source"],
        reference_id=task["reference_id"],
        operator_id=operator_id,
        reasoning_trace={
            "hitl_task_id": task_id,
            "trigger_reason": task["trigger_reason"],
            "justification_code": justification_code,
            "operator_id": operator_id,
            "original_amount": float(task["gross_amount"]),
            "final_amount": final_amount,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
        hitl_task_id=task_id,
    )

    return {**result, "task_id": task_id, "operator_id": operator_id, "status": "EXECUTED"}


async def reject_sweep(task_id: str, operator_id: str, reason: str) -> dict:
    """Human operator rejects a queued sweep."""
    client = supabase_service.get_client()
    row = (
        client.table("hitl_review_queue")
        .select("*")
        .eq("task_id", task_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if not row.data:
        raise KeyError(f"Task {task_id} not found or already resolved.")

    client.table("hitl_review_queue").update({
        "status": "rejected",
        "operator_id": operator_id,
        "justification_code": "REJECTED",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "operator_notes": {"rejection_reason": reason},
    }).eq("task_id", task_id).execute()

    logger.info(f"HITL REJECT: task={task_id}, operator={operator_id}, reason={reason}")
    return {"status": "REJECTED", "task_id": task_id, "operator_id": operator_id}


async def get_pending_queue() -> list[dict[str, Any]]:
    """Return all pending HITL reviews, oldest first."""
    client = supabase_service.get_client()
    result = (
        client.table("hitl_review_queue")
        .select("*")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []
