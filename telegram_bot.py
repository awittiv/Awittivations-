"""
telegram_bot.py — Telegram Bot helper for Awittivations AI Orchestrator

Requires environment variables:
    TELEGRAM_BOT_TOKEN  — from @BotFather
    TELEGRAM_PARSE_MODE — optional, defaults to "HTML"

Usage:
    import telegram_bot as tg
    await tg.send_message(chat_id, "Hello!")
"""

import os
import httpx
from typing import Any

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_BASE  = f"https://api.telegram.org/bot{_TOKEN}"
_PARSE = os.getenv("TELEGRAM_PARSE_MODE", "HTML")


# ─── Core helpers ─────────────────────────────────────────────────────────────

async def _post(method: str, payload: dict) -> dict:
    """POST to the Telegram Bot API and return the JSON response."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{_BASE}/{method}", json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_message(chat_id: int | str, text: str) -> dict:
    """Send an HTML-formatted message to a chat."""
    return await _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": _PARSE,
    })


async def send_typing(chat_id: int | str) -> dict:
    """Send a typing indicator to a chat."""
    return await _post("sendChatAction", {
        "chat_id": chat_id,
        "action": "typing",
    })


# ─── Formatters ───────────────────────────────────────────────────────────────

def format_response(result: dict[str, Any]) -> str:
    """Format an OrchestratorResponse dict as a Telegram HTML message."""
    agent     = result.get("agent", "Orchestrator")
    response  = result.get("response", "")
    actions   = result.get("actions", [])
    confidence = result.get("confidence", 0)
    blueprint = result.get("blueprint_type", "")

    agent_icons = {
        "CashPilot":    "◈",
        "Bankit":       "◎",
        "PulseAI":      "◉",
        "Orchestrator": "⬡",
    }
    icon = agent_icons.get(agent, "⬡")

    lines = [
        f"{icon} <b>{agent}</b>  <i>({blueprint} · {confidence}% confidence)</i>",
        "",
        response,
    ]

    if actions:
        lines += ["", "<b>Next steps:</b>"]
        lines += [f"  • {a}" for a in actions]

    return "\n".join(lines)


def format_review_request(result: dict[str, Any]) -> str:
    """Format a human-review escalation message."""
    reason   = result.get("review_reason", "Manual review required.")
    agent    = result.get("agent", "Orchestrator")
    response = result.get("response", "")

    return (
        f"⚠ <b>Human Review Required</b>\n\n"
        f"<b>Agent:</b> {agent}\n"
        f"<b>Reason:</b> {reason}\n\n"
        f"{response}\n\n"
        f"<i>A team member will follow up with you shortly.</i>"
    )


# ─── Webhook management ───────────────────────────────────────────────────────

async def register_webhook(base_url: str) -> dict:
    """Register the Telegram webhook. Call once after deployment."""
    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
    return await _post("setWebhook", {"url": webhook_url})


async def get_webhook_info() -> dict:
    """Return current Telegram webhook registration info."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{_BASE}/getWebhookInfo")
        resp.raise_for_status()
        return resp.json()
