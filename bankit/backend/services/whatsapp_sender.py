"""
Service: whatsapp_sender.py
Sends WhatsApp messages via Twilio.
Degrades gracefully to console logging when Twilio credentials are not configured
so the pipeline still works in dev without a live Twilio account.
"""

import os
import logging

logger = logging.getLogger(__name__)

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

_client = None


def _get_client():
    global _client
    if _client is None:
        from twilio.rest import Client
        _client = Client(TWILIO_SID, TWILIO_TOKEN)
    return _client


async def send_whatsapp(to_phone: str, message: str) -> bool:
    """
    Send a WhatsApp message to a phone number (E.164 format, e.g. +919876543210).
    Returns True if sent, False if skipped or failed.
    """
    if not TWILIO_SID or not TWILIO_TOKEN:
        logger.info(f"[WhatsApp:dev] → {to_phone}: {message[:80]}{'...' if len(message) > 80 else ''}")
        return False

    try:
        client = _get_client()
        client.messages.create(
            from_=TWILIO_FROM,
            to=f"whatsapp:{to_phone}",
            body=message,
        )
        logger.info(f"[WhatsApp] Sent to {to_phone}")
        return True
    except Exception as e:
        logger.error(f"[WhatsApp] Send failed to {to_phone}: {e}")
        return False
