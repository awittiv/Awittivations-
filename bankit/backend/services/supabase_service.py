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
    result = client.table("merchants").select("*").eq("phone", phone).limit(1).execute()
    return result.data[0] if result.data else None


async def get_merchant_by_id(merchant_id: str) -> dict | None:
    client = get_client()
    result = client.table("merchants").select("*").eq("id", merchant_id).limit(1).execute()
    return result.data[0] if result.data else None


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
    result = client.table("loans").select("*, loan_messages(*)").eq("id", loan_id).limit(1).execute()
    return result.data[0] if result.data else None


async def add_loan_message(loan_id: str, direction: str, content: str) -> dict:
    client = get_client()
    result = client.table("loan_messages").insert({
        "loan_id": loan_id,
        "direction": direction,
        "content": content,
    }).execute()
    return result.data[0]


async def claim_disbursement(loan_id: str) -> bool:
    """Atomically reserve a loan for disbursement. Returns True only once; concurrent callers get False."""
    client = get_client()
    result = (
        client.table("loans")
        .update({"tx_hash": "PENDING"})
        .eq("id", loan_id)
        .eq("status", "approved")
        .is_("tx_hash", "null")
        .execute()
    )
    return len(result.data) > 0


async def claim_repayment(loan_id: str) -> bool:
    """Atomically mark a loan as repaid. Returns True only once; concurrent callers get False."""
    client = get_client()
    result = (
        client.table("loans")
        .update({"status": "repaid"})
        .eq("id", loan_id)
        .eq("status", "disbursed")
        .execute()
    )
    return len(result.data) > 0


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
    loans = client.table("loans").select("id, amount_inr").eq("merchant_id", merchant_id).execute()
    if not loans.data:
        return []
    loan_ids = [ln["id"] for ln in loans.data]
    txs = (
        client.table("transactions")
        .select("amount, loan_id, created_at")
        .in_("loan_id", loan_ids)
        .eq("type", "repay")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        {"amount": tx["amount"], "status": "repaid", "loan_id": tx["loan_id"], "repaid_at": tx["created_at"]}
        for tx in (txs.data or [])
    ]


async def create_kyc_document(
    merchant_id: str, doc_type: str, storage_path: str, file_name: str
) -> dict:
    client = get_client()
    result = client.table("kyc_documents").upsert(
        {"merchant_id": merchant_id, "doc_type": doc_type, "storage_path": storage_path, "file_name": file_name},
        on_conflict="merchant_id,doc_type",
    ).execute()
    return result.data[0]


async def get_kyc_documents(merchant_id: str) -> list[dict]:
    client = get_client()
    result = client.table("kyc_documents").select("*").eq("merchant_id", merchant_id).order("created_at").execute()
    return result.data or []


def get_signed_kyc_url(storage_path: str) -> str:
    client = get_client()
    try:
        result = client.storage.from_("kyc-docs").create_signed_url(storage_path, 3600)
        if hasattr(result, "signed_url"):
            return result.signed_url or ""
        if isinstance(result, dict):
            return (result.get("data") or {}).get("signedURL", "") or result.get("signedURL", "")
    except Exception:
        pass
    return ""
