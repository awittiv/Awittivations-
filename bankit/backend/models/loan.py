from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class WhatsAppMessage(BaseModel):
    from_: str
    body: str


class WhatsAppWebhookPayload(BaseModel):
    messages: list[dict]


class CreateLoanRequest(BaseModel):
    amount_inr: float
    purpose: str


class LoanResponse(BaseModel):
    id: str
    merchant_id: str
    amount_inr: float
    purpose: str
    status: Literal["pending", "approved", "disbursed", "repaid", "rejected"]
    trust_score: int | None
    tx_hash: str | None
    error_reason: str | None = None
    created_at: datetime


class TrustScoreResult(BaseModel):
    score: int
    reasoning: str
    recommendation: Literal["approve", "reject", "review"]


class MerchantResponse(BaseModel):
    id: str
    user_id: str
    business_name: str
    phone: str | None
    wallet_address: str | None
    kyc_status: str
    created_at: datetime
