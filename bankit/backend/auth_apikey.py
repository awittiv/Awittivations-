import hashlib
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from services.supabase_service import get_client

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def get_api_key_record(x_api_key: str = Security(_header)) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")

    hashed = _hash(x_api_key)
    result = (
        get_client()
        .table("api_keys")
        .select("*")
        .eq("key_hash", hashed)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    record = result.data
    tier = record.get("tier", "starter")
    limit = {"starter": 100, "growth": 1000, "enterprise": 999999}.get(tier, 100)

    if record.get("requests_this_month", 0) >= limit:
        raise HTTPException(status_code=429, detail=f"Monthly limit reached for tier '{tier}'")

    return record


async def increment_usage(api_key_id: str) -> None:
    get_client().rpc("increment_api_key_usage", {"key_id": api_key_id}).execute()
