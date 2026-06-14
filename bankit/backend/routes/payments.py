from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Literal
from auth import get_current_merchant_id
from services import supabase_service
from services.sweep_engine import execute_atomic_sweep, get_sweep_summary

router = APIRouter(prefix="/payments", tags=["Payments"])


class IngestPaymentRequest(BaseModel):
    gross_amount: float = Field(..., gt=0, description="Gross revenue received in USD/INR")
    source: Literal["stripe", "w2g", "direct", "readybucks"] = "direct"
    reference_id: str | None = None


@router.post("/ingest")
async def ingest_payment(
    body: IngestPaymentRequest,
    merchant_id: str = Depends(get_current_merchant_id),
):
    """
    Ingest a payment and run the Atomic Sweep: withhold taxes at the millisecond
    of revenue ingest, credit only the net amount to the merchant's BKD wallet.
    """
    merchant = await supabase_service.get_merchant_by_id(merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    result = await execute_atomic_sweep(
        merchant_id=merchant_id,
        merchant_wallet=merchant.get("wallet_address"),
        gross_amount=body.gross_amount,
        source=body.source,
        reference_id=body.reference_id,
    )

    return {
        "sweep_id": result["sweep_id"],
        "gross_amount": result["gross_amount"],
        "withholding": {
            "mi_state": result["mi_state_withholding"],
            "muskegon_city": result["muskegon_city_withholding"],
            "federal_estimate": result["federal_withholding"],
            "total": result["total_withheld"],
            "effective_rate": result["effective_rate"],
        },
        "net_amount": result["net_amount"],
        "w2g_reportable": result["w2g_reportable"],
        "tx_hash": result["tx_hash"],
    }


@router.get("/sweep-summary")
async def sweep_summary(merchant_id: str = Depends(get_current_merchant_id)):
    """
    YTD Atomic Sweep summary for a merchant: gross earnings, total withheld
    by jurisdiction, net credited, and W-2G threshold status.
    """
    return await get_sweep_summary(merchant_id)


@router.get("/sweep-history")
async def sweep_history(merchant_id: str = Depends(get_current_merchant_id)):
    """Most recent 50 sweep records for the merchant."""
    client = supabase_service.get_client()
    result = (
        client.table("atomic_sweep_ledger")
        .select("*")
        .eq("merchant_id", merchant_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data or []
