"""
Service: whatsapp_pipeline.py
Wraps run_approval_pipeline and sends a WhatsApp notification to the merchant
with the final loan decision once the pipeline completes.
"""

import logging
from services.pipeline import run_approval_pipeline
from services.whatsapp_sender import send_whatsapp
from services import supabase_service

logger = logging.getLogger(__name__)


def _decision_message(
    status: str,
    amount_inr: float,
    trust_score: int | None,
    tx_hash: str | None,
    ai_reasoning: str | None = None,
) -> str:
    score_str = f"{trust_score}/100" if trust_score is not None else "N/A"
    reasoning_line = f"\n_{ai_reasoning}_" if ai_reasoning else ""

    if status == "disbursed":
        tx_preview = (tx_hash[:20] + "...") if tx_hash else "pending"
        return (
            f"✅ *Loan Approved & Disbursed!*\n"
            f"₹{amount_inr:,.0f} is on its way to your wallet.\n"
            f"Trust Score: {score_str}{reasoning_line}\n"
            f"TX: {tx_preview}\n\n"
            f"Reply *STATUS* to check your loan or *REPAY* when ready to repay."
        )
    if status == "approved":
        return (
            f"✅ *Loan Approved!*\n"
            f"₹{amount_inr:,.0f} approved. Disbursement is being processed.\n"
            f"Trust Score: {score_str}{reasoning_line}"
        )
    if status == "rejected":
        return (
            f"❌ *Application Not Approved*\n"
            f"Your request for ₹{amount_inr:,.0f} was not approved this time.\n"
            f"Trust Score: {score_str}{reasoning_line}\n\n"
            f"Tip: Maintaining regular repayments improves your score for next time."
        )
    # pending — under human review
    return (
        f"⏳ *Under Review*\n"
        f"Your application for ₹{amount_inr:,.0f} is being manually reviewed.\n"
        f"Trust Score: {score_str}\n\n"
        f"We'll notify you as soon as a decision is made."
    )


async def run_pipeline_and_notify(
    loan_id: str,
    merchant_id: str,
    phone: str,
    amount_inr: float,
) -> None:
    """Run the full approval pipeline then send the result to the merchant via WhatsApp."""
    try:
        await run_approval_pipeline(loan_id, merchant_id)

        loan = await supabase_service.get_loan_by_id(loan_id)
        if not loan:
            logger.error(f"[WA Pipeline] Loan {loan_id} not found after pipeline run")
            return

        message = _decision_message(
            status=loan["status"],
            amount_inr=amount_inr,
            trust_score=loan.get("trust_score"),
            tx_hash=loan.get("tx_hash"),
            ai_reasoning=loan.get("ai_reasoning"),
        )

        await supabase_service.add_loan_message(loan_id, "outbound", message)
        await send_whatsapp(phone, message)

    except Exception as e:
        logger.error(f"[WA Pipeline] Error for loan {loan_id}: {e}")
        await send_whatsapp(
            phone,
            "Sorry, we hit an issue processing your application. Please try again or visit bankit.app."
        )
