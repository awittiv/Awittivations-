from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from typing import Literal
from auth_admin import get_admin_user_id
from services import supabase_service
from services.web3_service import release_micro_liquidity, build_trust_score_hash
from services.sweep_engine import execute_atomic_sweep
from services.whatsapp_sender import send_whatsapp
from services.wallet_service import generate_new_master_seed, derive_oracle_wallet

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _notify_merchant(merchant_id: str, message: str) -> None:
    merchant = await supabase_service.get_merchant_by_id(merchant_id)
    phone = merchant.get("phone") if merchant else None
    if phone:
        await send_whatsapp(phone, message)


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
async def approve_loan(
    loan_id: str,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_admin_user_id),
):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve loan with status: {loan['status']}")

    updated = await supabase_service.update_loan(loan_id, {"status": "approved"})

    msg = (
        f"✅ *Loan Approved!*\n"
        f"Your application for ₹{float(loan['amount_inr']):,.0f} has been approved by our team.\n"
        f"Funds are being processed for disbursement to your wallet."
    )
    background_tasks.add_task(_notify_merchant, loan["merchant_id"], msg)
    return updated


@router.post("/loans/{loan_id}/reject")
async def reject_loan(
    loan_id: str,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_admin_user_id),
):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail=f"Cannot reject loan with status: {loan['status']}")

    updated = await supabase_service.update_loan(loan_id, {"status": "rejected"})

    score = loan.get("trust_score")
    score_str = f"{score}/100" if score is not None else "N/A"
    msg = (
        f"❌ *Application Not Approved*\n"
        f"Your request for ₹{float(loan['amount_inr']):,.0f} was not approved at this time.\n"
        f"Trust Score: {score_str}\n\n"
        f"Maintaining regular repayments improves your score for future applications."
    )
    background_tasks.add_task(_notify_merchant, loan["merchant_id"], msg)
    return updated


@router.post("/loans/{loan_id}/disburse")
async def disburse_loan(
    loan_id: str,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_admin_user_id),
):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Loan must be approved to disburse, current status: {loan['status']}",
        )

    merchant = await supabase_service.get_merchant_by_id(loan["merchant_id"])
    wallet_address = merchant.get("wallet_address") if merchant else None
    if not wallet_address:
        raise HTTPException(status_code=400, detail="Merchant has no wallet address on file")

    score = loan.get("trust_score") or 50
    trust_score_hash = build_trust_score_hash(loan_id, score, "admin-manual-disburse")
    tx_hash = await release_micro_liquidity(wallet_address, loan["amount_inr"], trust_score_hash)

    if not tx_hash:
        raise HTTPException(
            status_code=502,
            detail="On-chain disbursement failed — check wallet balance and RPC connection",
        )

    await supabase_service.update_loan(loan_id, {"status": "disbursed", "tx_hash": tx_hash})
    await supabase_service.create_transaction(loan_id, loan["amount_inr"], "disburse", tx_hash)

    # Atomic Sweep on admin-triggered disbursal (non-blocking)
    background_tasks.add_task(
        execute_atomic_sweep,
        loan["merchant_id"],
        wallet_address,
        float(loan["amount_inr"]),
        "loan_disbursal",
        loan_id,
    )

    tx_preview = tx_hash[:20] + "..."
    msg = (
        f"💸 *Funds Disbursed!*\n"
        f"₹{float(loan['amount_inr']):,.0f} has been sent to your Polygon wallet.\n"
        f"TX: {tx_preview}\n\n"
        f"Reply *STATUS* to check your loan or *REPAY* when ready to repay."
    )
    background_tasks.add_task(_notify_merchant, loan["merchant_id"], msg)

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


# ── Sovereign Wallet Admin ───────────────────────────────────────────────────

@router.get("/wallet/oracle")
async def get_oracle_wallet(_: str = Depends(get_admin_user_id)):
    """
    Return the oracle wallet address derived from WALLET_MASTER_SEED (index 0).
    Use this to fund the oracle with MATIC for gas.
    """
    try:
        address, _ = derive_oracle_wallet()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "oracle_address": address,
        "derivation_path": "m/44'/60'/0'/0/0",
        "note": "Fund this address with MATIC on Polygon Mainnet for contract deployment and gas.",
    }


@router.post("/wallet/generate-seed")
async def generate_master_seed(_: str = Depends(get_admin_user_id)):
    """
    Generate a fresh 24-word BIP-39 master seed.
    ONLY call this during initial setup. Save the mnemonic immediately —
    it controls all sovereign merchant wallets. Set it as WALLET_MASTER_SEED.
    """
    mnemonic = generate_new_master_seed()
    return {
        "mnemonic": mnemonic,
        "warning": "BACK THIS UP NOW. Store in a secrets manager. Losing it loses all sovereign wallets.",
        "next_step": "Set WALLET_MASTER_SEED=<mnemonic> in your environment, then restart the server.",
    }
