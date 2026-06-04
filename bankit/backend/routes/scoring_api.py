from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal
from auth_apikey import get_api_key_record, increment_usage
from services.trust_score import score_loan_request

router = APIRouter(prefix="/v1", tags=["Scoring API"])


class ScoreRequest(BaseModel):
    business_name: str
    amount_inr: float = Field(..., gt=0, description="Loan amount in INR")
    purpose: str
    merchant_age_days: int = Field(0, ge=0)
    repayment_history: list[dict] = Field(default_factory=list)


class ScoreResponse(BaseModel):
    score: int
    reasoning: str
    recommendation: Literal["approve", "reject", "review"]
    tier: str
    requests_remaining: int


@router.post("/score", response_model=ScoreResponse)
async def score(body: ScoreRequest, api_key: dict = Depends(get_api_key_record)):
    result = await score_loan_request(
        amount_inr=body.amount_inr,
        purpose=body.purpose,
        business_name=body.business_name,
        repayment_history=body.repayment_history,
        merchant_age_days=body.merchant_age_days,
    )

    await increment_usage(api_key["id"])

    tier = api_key.get("tier", "starter")
    limit = {"starter": 100, "growth": 1000, "enterprise": 999999}.get(tier, 100)
    used = api_key.get("requests_this_month", 0) + 1

    return ScoreResponse(
        score=result.score,
        reasoning=result.reasoning,
        recommendation=result.recommendation,
        tier=tier,
        requests_remaining=max(0, limit - used),
    )
