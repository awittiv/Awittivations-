from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Literal
from auth_admin import get_admin_user_id
from services import supabase_service
from services.web3_service import release_micro_liquidity, build_trust_score_hash

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/loans")
async def list_all_loans(_: str = Depends(get_admin_user_id)):
    client = supabase_service.get_client()
    result = (
        client.table("loans")
        .select("*, merchants(business_name, phone, wallet_address)")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("/loans/{loan_id}/approve")
async def approve_loan(loan_id: str, _: str = Depends(get_admin_user_id)):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve loan with status: {loan['status']}")
    return await supabase_service.update_loan(loan_id, {"status": "approved"})


@router.post("/loans/{loan_id}/reject")
async def reject_loan(loan_id: str, _: str = Depends(get_admin_user_id)):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail=f"Cannot reject loan with status: {loan['status']}")
    return await supabase_service.update_loan(loan_id, {"status": "rejected"})


@router.post("/loans/{loan_id}/disburse")
async def disburse_loan(loan_id: str, _: str = Depends(get_admin_user_id)):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] != "approved":
        raise HTTPException(status_code=400, detail=f"Loan must be approved to disburse, current status: {loan['status']}")

    merchant = await supabase_service.get_merchant_by_id(loan["merchant_id"])
    wallet_address = merchant.get("wallet_address") if merchant else None
    if not wallet_address:
        raise HTTPException(status_code=400, detail="Merchant has no wallet address on file")

    score = loan.get("trust_score") or 50
    trust_score_hash = build_trust_score_hash(loan_id, score, "admin-manual-disburse")
    tx_hash = await release_micro_liquidity(wallet_address, loan["amount_inr"], trust_score_hash)

    if not tx_hash:
        raise HTTPException(status_code=502, detail="On-chain disbursement failed — check wallet balance and RPC connection")

    await supabase_service.update_loan(loan_id, {"status": "disbursed", "tx_hash": tx_hash})
    await supabase_service.create_transaction(loan_id, loan["amount_inr"], "disburse", tx_hash)
    return await supabase_service.get_loan_by_id(loan_id)


@router.get("/merchants")
async def list_all_merchants(_: str = Depends(get_admin_user_id)):
    client = supabase_service.get_client()
    result = client.table("merchants").select("*").order("created_at", desc=True).execute()
    return result.data


class KycUpdate(BaseModel):
    status: Literal["pending", "under_review", "verified", "rejected"]


@router.patch("/merchants/{merchant_id}/kyc")
async def update_kyc(merchant_id: str, body: KycUpdate, _: str = Depends(get_admin_user_id)):
    return await supabase_service.update_merchant(merchant_id, {"kyc_status": body.status})


@router.get("/merchants/{merchant_id}/kyc-docs")
async def get_merchant_kyc_docs(merchant_id: str, _: str = Depends(get_admin_user_id)):
    docs = await supabase_service.get_kyc_documents(merchant_id)
    return [
        {**doc, "signed_url": supabase_service.get_signed_kyc_url(doc["storage_path"])}
        for doc in docs
    ]
