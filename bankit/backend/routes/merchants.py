from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Literal
from models.loan import MerchantResponse
from services import supabase_service
from services.wallet_service import assign_sovereign_wallet
from services.web3_service import get_passport_token_id, PASSPORT_ADDRESS
from auth import get_current_merchant_id

router = APIRouter()


@router.get("/merchants/me", response_model=MerchantResponse)
async def get_my_merchant(current_merchant_id: str = Depends(get_current_merchant_id)):
    merchant = await supabase_service.get_merchant_by_id(current_merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.get("/merchants/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: str,
    current_merchant_id: str = Depends(get_current_merchant_id),
):
    if merchant_id != current_merchant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    merchant = await supabase_service.get_merchant_by_id(merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


class KycDocSubmit(BaseModel):
    doc_type: Literal["aadhaar", "pan", "gst"]
    storage_path: str
    file_name: str


@router.post("/merchants/{merchant_id}/kyc/submit")
async def submit_kyc_doc(
    merchant_id: str,
    body: KycDocSubmit,
    current_merchant_id: str = Depends(get_current_merchant_id),
):
    if merchant_id != current_merchant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await supabase_service.create_kyc_document(
        merchant_id, body.doc_type, body.storage_path, body.file_name
    )

    merchant = await supabase_service.get_merchant_by_id(merchant_id)
    if merchant and merchant.get("kyc_status") != "verified":
        await supabase_service.update_merchant(merchant_id, {"kyc_status": "under_review"})

    return {"status": "submitted", "doc_type": body.doc_type}


@router.post("/merchants/{merchant_id}/wallet/init")
async def init_sovereign_wallet(
    merchant_id: str,
    current_merchant_id: str = Depends(get_current_merchant_id),
):
    """
    Assign a BIP-44 sovereign wallet to the merchant (idempotent).
    Called once after signup — gives the merchant a Polygon address
    without requiring MetaMask or any external wallet setup.
    """
    if merchant_id != current_merchant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        result = await assign_sovereign_wallet(merchant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return result


@router.get("/merchants/{merchant_id}/wallet")
async def get_wallet(
    merchant_id: str,
    current_merchant_id: str = Depends(get_current_merchant_id),
):
    """Return the merchant's sovereign wallet address and on-chain balance."""
    if merchant_id != current_merchant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    merchant = await supabase_service.get_merchant_by_id(merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    wallet_address = merchant.get("wallet_address")
    wallet_index   = merchant.get("wallet_index")

    if not wallet_address:
        return {
            "has_wallet": False,
            "message": "No wallet yet. POST /merchants/{id}/wallet/init to create one.",
        }

    # Fetch on-chain BKD balance
    bkd_balance = None
    try:
        from services.web3_service import get_web3
        import os
        stablecoin_addr = os.getenv("STABLECOIN_ADDRESS", "")
        if stablecoin_addr and stablecoin_addr != "0x0000000000000000000000000000000000000000":
            ERC20_BALANCE_ABI = [{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
            w3 = get_web3()
            token = w3.eth.contract(address=stablecoin_addr, abi=ERC20_BALANCE_ABI)
            raw = token.functions.balanceOf(wallet_address).call()
            bkd_balance = raw / (10 ** 6)
    except Exception:
        pass

    return {
        "has_wallet": True,
        "wallet_address": wallet_address,
        "sovereign": wallet_index is not None,
        "wallet_index": wallet_index,
        "bkd_balance": bkd_balance,
        "chain": "Polygon",
        "polygonscan_url": f"https://polygonscan.com/address/{wallet_address}",
    }


@router.get("/merchants/{merchant_id}/passport")
async def get_credit_passport(
    merchant_id: str,
    current_merchant_id: str = Depends(get_current_merchant_id),
):
    """Return the merchant's on-chain Bankit Credit Passport metadata."""
    if merchant_id != current_merchant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    token_id = get_passport_token_id(merchant_id)
    if token_id is None:
        return {
            "has_passport": False,
            "message": "No Credit Passport yet — complete a loan to earn your on-chain credit identity.",
        }
    polygonscan_base = "https://polygonscan.com/token"
    return {
        "has_passport": True,
        "token_id": token_id,
        "contract_address": PASSPORT_ADDRESS,
        "polygonscan_url": f"{polygonscan_base}/{PASSPORT_ADDRESS}?a={token_id}",
        "standard": "ERC-721 / ERC-5192 Soulbound",
        "chain": "Polygon",
    }


@router.get("/merchants/{merchant_id}/kyc/documents")
async def list_kyc_documents(
    merchant_id: str,
    current_merchant_id: str = Depends(get_current_merchant_id),
):
    if merchant_id != current_merchant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    docs = await supabase_service.get_kyc_documents(merchant_id)
    return [
        {**doc, "signed_url": supabase_service.get_signed_kyc_url(doc["storage_path"])}
        for doc in docs
    ]
