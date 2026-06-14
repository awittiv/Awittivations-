"""
Multi-agent AI underwriting: three specialist Claude agents run in parallel,
then an orchestrator synthesizes a final credit decision.

Agents:
  FraudDetection   — anomaly signals, account age vs. amount
  CreditAnalysis   — repayment history, velocity, trend
  PurposeViability — business legitimacy and amount-fit

Parallel execution via asyncio.gather reduces latency vs. a single sequential call.
"""

import asyncio
import os
import json
import anthropic
from models.loan import TrustScoreResult

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _client


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.split("\n")
        return "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text


async def _call_agent(prompt: str, max_tokens: int = 300) -> dict:
    """Run one specialist agent call in a thread pool (SDK is sync)."""
    client = get_client()
    loop = asyncio.get_event_loop()
    message = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    return json.loads(_strip_fences(message.content[0].text.strip()))


async def _fraud_agent(amount_inr: float, purpose: str, merchant_age_days: int, prior_count: int) -> dict:
    prompt = f"""You are a fraud detection specialist for Bankit, a microloan platform in India.
Assess fraud risk for this application. Return ONLY valid JSON.

Amount: ₹{amount_inr:,.0f}
Purpose: {purpose}
Account age: {merchant_age_days} days
Prior loans on platform: {prior_count}

Return:
{{"fraud_risk": "low|medium|high", "signals": ["<signal>", ...], "score_penalty": <integer 0-30>}}

Signals to evaluate:
- New account (< 30 days) requesting > ₹20,000 → high risk
- Vague purpose ("personal use", "investment", "misc") → medium/high
- First loan at maximum amount with no history → medium
- Round numbers + vague purpose combo → medium
- Legitimate inventory/equipment with seasoned account → low"""
    try:
        return await _call_agent(prompt)
    except Exception as exc:
        return {"fraud_risk": "medium", "signals": [f"agent error: {exc}"], "score_penalty": 10}


async def _credit_agent(repayment_history: list[dict], merchant_age_days: int) -> dict:
    history_text = "No prior loans on platform." if not repayment_history else "\n".join(
        f"- ₹{r['amount']} ({r['status']})" for r in repayment_history
    )
    prompt = f"""You are a credit analyst for Bankit, a microloan platform in India.
Analyze this merchant's repayment history. Return ONLY valid JSON.

Account age: {merchant_age_days} days
Repayment history:
{history_text}

Return:
{{"credit_score": <integer 0-100>, "trend": "improving|stable|declining|thin", "reasoning": "<one sentence>"}}

Scoring guide:
- 100% repaid, 3+ loans → 85–100
- 100% repaid, 1–2 loans → 70–84
- No history → 50 (neutral baseline)
- Mixed history (some late/missed) → 30–49
- Defaults present → 0–29"""
    try:
        return await _call_agent(prompt)
    except Exception as exc:
        return {"credit_score": 50, "trend": "thin", "reasoning": f"Credit agent error: {exc}"}


async def _purpose_agent(purpose: str, amount_inr: float) -> dict:
    prompt = f"""You are a business viability assessor for Bankit, a microloan platform for small merchants in India.
Evaluate whether this loan purpose is legitimate and the amount is proportionate. Return ONLY valid JSON.

Purpose: {purpose}
Amount: ₹{amount_inr:,.0f}

Return:
{{"viability": "strong|moderate|weak", "purpose_score": <integer 0-100>, "reasoning": "<one sentence>"}}

Scoring guide:
- Strong (75–100): Specific business need (rice/fuel/equipment inventory), proportionate amount
- Moderate (45–74): General business mention, somewhat vague but plausible
- Weak (0–44): Personal use, speculative investment, amount wildly out of proportion"""
    try:
        return await _call_agent(prompt)
    except Exception as exc:
        return {"viability": "moderate", "purpose_score": 50, "reasoning": f"Purpose agent error: {exc}"}


async def score_loan_request(
    amount_inr: float,
    purpose: str,
    business_name: str,
    repayment_history: list[dict] | None = None,
    merchant_age_days: int = 0,
) -> TrustScoreResult:
    history = repayment_history or []

    # Three specialists run in parallel — total latency ≈ slowest single call
    fraud_r, credit_r, purpose_r = await asyncio.gather(
        _fraud_agent(amount_inr, purpose, merchant_age_days, len(history)),
        _credit_agent(history, merchant_age_days),
        _purpose_agent(purpose, amount_inr),
    )

    credit_score  = max(0, min(100, int(credit_r.get("credit_score", 50))))
    purpose_score = max(0, min(100, int(purpose_r.get("purpose_score", 50))))
    fraud_penalty = max(0, min(30,  int(fraud_r.get("score_penalty", 10))))
    fraud_risk    = fraud_r.get("fraud_risk", "medium")

    # Weighted composite: credit history 50%, purpose fit 35%, baseline 15%
    raw = (credit_score * 0.50) + (purpose_score * 0.35) + (50 * 0.15)
    final_score = max(0, min(100, round(raw - fraud_penalty)))

    # Hard ceiling for high-fraud signals — AI cannot override the fraud gate
    if fraud_risk == "high":
        final_score = min(final_score, 34)

    recommendation = (
        "approve" if final_score >= 65
        else "reject" if final_score < 40
        else "review"
    )

    # Compose human-readable reasoning from specialist outputs
    parts = [
        credit_r.get("reasoning", ""),
        purpose_r.get("reasoning", ""),
    ]
    if fraud_risk != "low":
        signals = fraud_r.get("signals", [])
        if signals:
            parts.append(f"Fraud flag: {signals[0]}.")
    reasoning = " | ".join(p for p in parts if p).strip()
    if not reasoning:
        reasoning = (
            f"Multi-agent: credit={credit_score}, purpose={purpose_score}, "
            f"fraud={fraud_risk}, net={final_score}."
        )

    return TrustScoreResult(
        score=final_score,
        reasoning=reasoning,
        recommendation=recommendation,
    )
