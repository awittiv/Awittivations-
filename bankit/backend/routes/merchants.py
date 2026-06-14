from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Literal
from models.loan import MerchantResponse
from services import supabase_service
from auth import get_current_merchant_id

router = APIRouter()


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
