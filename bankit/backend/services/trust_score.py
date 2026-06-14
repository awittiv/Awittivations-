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


async def score_loan_request(
    amount_inr: float,
    purpose: str,
    business_name: str,
    repayment_history: list[dict] | None = None,
    merchant_age_days: int = 0,
) -> TrustScoreResult:
    history_text = "No prior loans." if not repayment_history else "\n".join(
        f"- ₹{r['amount']} ({r['status']})" for r in repayment_history
    )

    prompt = f"""You are an AI credit underwriter for Bankit, a microloan platform serving small merchants in India.

Evaluate this loan application and return a JSON trust score.

Business: {business_name}
Merchant account age: {merchant_age_days} days
Loan requested: ₹{amount_inr:,.0f}
Purpose: {purpose}
Repayment history:
{history_text}

Return ONLY valid JSON with this exact structure:
{{
  "score": <integer 0-100>,
  "reasoning": "<one sentence explanation>",
  "recommendation": "<approve|reject|review>"
}}

Scoring guidelines:
- approve: score >= 65
- review: score 40-64
- reject: score < 40

Consider: loan size vs business maturity, purpose legitimacy, repayment history, and reasonableness."""

    client = get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()

    # Strip markdown code fences if Claude wraps JSON in ```json ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
        score = max(0, min(100, int(data["score"])))
        recommendation = data["recommendation"]
        if recommendation not in ("approve", "reject", "review"):
            recommendation = "review"
        return TrustScoreResult(
            score=score,
            reasoning=str(data.get("reasoning", "AI scorer returned no reasoning.")),
            recommendation=recommendation,
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        # Fall back to manual review rather than crashing the pipeline
        return TrustScoreResult(
            score=50,
            reasoning=f"Scoring model returned unparseable response — flagged for manual review. ({exc})",
            recommendation="review",
        )
