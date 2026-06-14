import os
from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        _client = create_client(url, key)
    return _client


async def get_merchant_by_phone(phone: str) -> dict | None:
    client = get_client()
    result = client.table("merchants").select("*").eq("phone", phone).single().execute()
    return result.data


async def get_merchant_by_id(merchant_id: str) -> dict | None:
    client = get_client()
    result = client.table("merchants").select("*").eq("id", merchant_id).single().execute()
    return result.data


async def create_loan(merchant_id: str, amount_inr: float, purpose: str) -> dict:
    client = get_client()
    result = client.table("loans").insert({
        "merchant_id": merchant_id,
        "amount_inr": amount_inr,
        "purpose": purpose,
        "status": "pending",
    }).execute()
    return result.data[0]


async def update_loan(loan_id: str, updates: dict) -> dict:
    client = get_client()
    result = client.table("loans").update(updates).eq("id", loan_id).execute()
    return result.data[0]


async def get_loans_for_merchant(merchant_id: str) -> list[dict]:
    client = get_client()
    result = client.table("loans").select("*").eq("merchant_id", merchant_id).order("created_at", desc=True).execute()
    return result.data


async def get_loan_by_id(loan_id: str) -> dict | None:
    client = get_client()
    result = client.table("loans").select("*, loan_messages(*)").eq("id", loan_id).single().execute()
    return result.data


async def add_loan_message(loan_id: str, direction: str, content: str) -> dict:
    client = get_client()
    result = client.table("loan_messages").insert({
        "loan_id": loan_id,
        "direction": direction,
        "content": content,
    }).execute()
    return result.data[0]


async def create_transaction(loan_id: str, amount: float, tx_type: str, polygon_tx_hash: str | None = None) -> dict:
    client = get_client()
    result = client.table("transactions").insert({
        "loan_id": loan_id,
        "amount": amount,
        "type": tx_type,
        "polygon_tx_hash": polygon_tx_hash,
    }).execute()
    return result.data[0]


async def update_merchant(merchant_id: str, updates: dict) -> dict:
    client = get_client()
    result = client.table("merchants").update(updates).eq("id", merchant_id).execute()
    return result.data[0]


async def get_repayment_history(merchant_id: str) -> list[dict]:
    client = get_client()
    loans = client.table("loans").select("id").eq("merchant_id", merchant_id).execute()
    if not loans.data:
        return []
    loan_ids = [l["id"] for l in loans.data]
    txs = client.table("transactions").select("amount").in_("loan_id", loan_ids).eq("type", "repay").execute()
    return [{"amount": tx["amount"], "status": "repaid"} for tx in (txs.data or [])]
