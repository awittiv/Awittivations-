from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from models.loan import CreateLoanRequest, LoanResponse
from services import supabase_service
from services.pipeline import run_approval_pipeline
from services.web3_service import repay_loan_onchain
from auth import get_current_merchant_id

router = APIRouter()


@router.get("/loans", response_model=list[LoanResponse])
async def list_loans(merchant_id: str = Depends(get_current_merchant_id)):
    return await supabase_service.get_loans_for_merchant(merchant_id)


@router.post("/loans", response_model=LoanResponse, status_code=201)
async def create_loan(
    body: CreateLoanRequest,
    background_tasks: BackgroundTasks,
    merchant_id: str = Depends(get_current_merchant_id),
):
    loan = await supabase_service.create_loan(merchant_id, body.amount_inr, body.purpose)
    background_tasks.add_task(run_approval_pipeline, loan["id"], merchant_id)
    return loan


@router.get("/loans/{loan_id}", response_model=LoanResponse)
async def get_loan(loan_id: str, merchant_id: str = Depends(get_current_merchant_id)):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan or loan["merchant_id"] != merchant_id:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@router.post("/loans/{loan_id}/repay", response_model=LoanResponse)
async def repay_loan(loan_id: str, merchant_id: str = Depends(get_current_merchant_id)):
    loan = await supabase_service.get_loan_by_id(loan_id)
    if not loan or loan["merchant_id"] != merchant_id:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan["status"] != "disbursed":
        raise HTTPException(status_code=400, detail=f"Loan cannot be repaid — current status: {loan['status']}")

    merchant = await supabase_service.get_merchant_by_id(loan["merchant_id"])
    wallet_address = merchant.get("wallet_address") if merchant else None
    tx_hash = await repay_loan_onchain(wallet_address, loan["amount_inr"], loan_id) if wallet_address else None

    await supabase_service.create_transaction(loan_id, loan["amount_inr"], "repay", tx_hash)
    updated = await supabase_service.update_loan(loan_id, {"status": "repaid"})
    return updated
