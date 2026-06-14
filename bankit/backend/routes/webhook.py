import os
import logging

from fastapi import APIRouter, BackgroundTasks, Form, Request, HTTPException

from services import supabase_service, whatsapp_parser
from services.whatsapp_sender import send_whatsapp, TWILIO_TOKEN
from services.whatsapp_pipeline import run_pipeline_and_notify
from services.web3_service import repay_loan_onchain

logger = logging.getLogger(__name__)

router = APIRouter()

HELP_MESSAGE = (
    "👋 *Welcome to Bankit!*\n\n"
    "Here's what you can do:\n"
    "• *Apply*: 'I need ₹5000 for rice inventory'\n"
    "• *Status*: 'What is my loan status?'\n"
    "• *Repay*: 'I want to repay my loan'\n"
    "• *Balance*: 'What do I owe?'\n\n"
    "Need help? Visit bankit.app"
)

MIN_AMOUNT = 100
MAX_AMOUNT = 100_000


def _classify_intent(body: str) -> str:
    lower = body.lower().strip()
    if any(w in lower for w in ["status", "update", "my loan", "application"]):
        return "status"
    if any(w in lower for w in ["repay", "pay back", "clear loan", "settle", "settlement"]):
        return "repay"
    if any(w in lower for w in ["balance", "owe", "outstanding", "due"]):
        return "balance"
    if any(w in lower for w in ["help", "hi", "hello", "start", "menu", "?"]):
        return "help"
    return "apply"


async def _handle_status(merchant: dict, phone: str) -> dict:
    loans = await supabase_service.get_loans_for_merchant(merchant["id"])
    if not loans:
        reply = "You have no loan applications yet.\n\nSend a message like 'I need ₹5000 for rice inventory' to apply."
        await send_whatsapp(phone, reply)
        return {"status": "no_loans", "reply": reply}

    latest = loans[0]
    status_emoji = {
        "pending": "⏳", "approved": "✅", "disbursed": "💸", "repaid": "🎉", "rejected": "❌"
    }.get(latest["status"], "•")
    score_str = f"{latest['trust_score']}/100" if latest.get("trust_score") else "scoring..."

    reply = (
        f"{status_emoji} *Latest Loan Status*\n"
        f"Purpose: {latest['purpose']}\n"
        f"Amount: ₹{float(latest['amount_inr']):,.0f}\n"
        f"Status: {latest['status'].upper()}\n"
        f"Trust Score: {score_str}"
    )

    await send_whatsapp(phone, reply)
    return {"status": "status_sent", "loan_id": latest["id"], "reply": reply}


async def _handle_repay(merchant: dict, phone: str) -> dict:
    loans = await supabase_service.get_loans_for_merchant(merchant["id"])
    disbursed = [l for l in loans if l["status"] == "disbursed"]

    if not disbursed:
        active = [l for l in loans if l["status"] in ("pending", "approved")]
        if active:
            reply = f"Your loan is still being processed (status: {active[0]['status']}). No repayment needed yet."
        else:
            reply = "You have no active loans to repay."
        await send_whatsapp(phone, reply)
        return {"status": "no_active_loan", "reply": reply}

    loan = disbursed[0]
    wallet_address = merchant.get("wallet_address")
    tx_hash = await repay_loan_onchain(wallet_address, loan["amount_inr"], loan["id"]) if wallet_address else None

    await supabase_service.create_transaction(loan["id"], loan["amount_inr"], "repay", tx_hash)
    await supabase_service.update_loan(loan["id"], {"status": "repaid"})

    reply = (
        f"🎉 *Repayment Received!*\n"
        f"₹{float(loan['amount_inr']):,.0f} repaid successfully.\n\n"
        f"Thank you! Your repayment history helps improve your trust score for future loans."
    )
    await supabase_service.add_loan_message(loan["id"], "outbound", reply)
    await send_whatsapp(phone, reply)
    return {"status": "repaid", "loan_id": loan["id"], "reply": reply}


async def _handle_balance(merchant: dict, phone: str) -> dict:
    loans = await supabase_service.get_loans_for_merchant(merchant["id"])
    disbursed = [l for l in loans if l["status"] == "disbursed"]

    if not disbursed:
        reply = "You have no outstanding balance. You're all clear! 🎉"
        await send_whatsapp(phone, reply)
        return {"status": "no_balance", "reply": reply}

    total_owed = sum(float(l["amount_inr"]) for l in disbursed)
    reply = (
        f"💰 *Outstanding Balance*\n"
        f"Total owed: ₹{total_owed:,.0f}\n"
        f"Active loans: {len(disbursed)}\n\n"
        f"Reply *REPAY* to repay your loan."
    )
    await send_whatsapp(phone, reply)
    return {"status": "balance_sent", "reply": reply}


async def _handle_apply(
    merchant: dict,
    phone: str,
    body: str,
    background_tasks: BackgroundTasks,
) -> dict:
    # Block if merchant already has an active disbursed loan
    existing = await supabase_service.get_loans_for_merchant(merchant["id"])
    if any(l["status"] == "disbursed" for l in existing):
        active = next(l for l in existing if l["status"] == "disbursed")
        reply = (
            f"You already have an active loan of ₹{float(active['amount_inr']):,.0f}.\n"
            f"Please repay it before applying for a new one.\n\n"
            f"Reply *REPAY* to repay now."
        )
        await send_whatsapp(phone, reply)
        return {"status": "active_loan_exists", "reply": reply}

    amount, purpose = whatsapp_parser.parse_loan_request(body)

    if amount is None:
        reply = (
            "I couldn't find a loan amount in your message.\n\n"
            "Try: *I need ₹5000 for rice inventory*"
        )
        await send_whatsapp(phone, reply)
        return {"status": "parse_error", "reply": reply}

    if not (MIN_AMOUNT <= amount <= MAX_AMOUNT):
        reply = (
            f"Loan amount must be between ₹{MIN_AMOUNT:,} and ₹{MAX_AMOUNT:,}.\n"
            f"You requested ₹{amount:,.0f}."
        )
        await send_whatsapp(phone, reply)
        return {"status": "amount_out_of_range", "reply": reply}

    loan = await supabase_service.create_loan(merchant["id"], amount, purpose or body)
    await supabase_service.add_loan_message(loan["id"], "inbound", body)

    ack = (
        f"📋 *Application Received!*\n"
        f"₹{amount:,.0f} for '{purpose or body}'\n\n"
        f"Running credit check now... you'll hear back in seconds."
    )
    await supabase_service.add_loan_message(loan["id"], "outbound", ack)
    await send_whatsapp(phone, ack)

    background_tasks.add_task(
        run_pipeline_and_notify,
        loan["id"],
        merchant["id"],
        phone,
        amount,
    )

    return {"status": "processing", "loan_id": loan["id"], "reply": ack}


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    From: str = Form(""),
    Body: str = Form(""),
):
    # Twilio signature verification — skip in dev when token not configured
    if TWILIO_TOKEN:
        try:
            from twilio.request_validator import RequestValidator
            form_data = dict(await request.form())
            signature = request.headers.get("X-Twilio-Signature", "")
            # Use WEBHOOK_BASE_URL if set (needed behind Railway's proxy)
            base_url = os.getenv("WEBHOOK_BASE_URL", str(request.url))
            validator = RequestValidator(TWILIO_TOKEN)
            if not validator.validate(base_url, form_data, signature):
                logger.warning("[Webhook] Invalid Twilio signature from %s", request.client)
                raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        except ImportError:
            pass  # twilio package not installed — skip verification

    # Twilio sends From=whatsapp:+919876543210
    phone = From.replace("whatsapp:", "").strip()
    body = Body.strip()

    if not phone or not body:
        return {"status": "missing_fields"}

    merchant = await supabase_service.get_merchant_by_phone(phone)
    if not merchant:
        reply = (
            "👋 Welcome to Bankit!\n\n"
            "You're not registered yet. Sign up at bankit.app to access microloans."
        )
        await send_whatsapp(phone, reply)
        return {"status": "unregistered", "reply": reply}

    intent = _classify_intent(body)

    if intent == "status":
        return await _handle_status(merchant, phone)
    if intent == "repay":
        return await _handle_repay(merchant, phone)
    if intent == "balance":
        return await _handle_balance(merchant, phone)
    if intent == "help":
        await send_whatsapp(phone, HELP_MESSAGE)
        return {"status": "help_sent", "reply": HELP_MESSAGE}

    return await _handle_apply(merchant, phone, body, background_tasks)
