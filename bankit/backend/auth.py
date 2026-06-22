import os
from fastapi import HTTPException, Header
from jose import jwt, JWTError

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


async def get_current_merchant_id(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")

    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"])
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate token")

    from services.supabase_service import get_client
    result = get_client().table("merchants").select("id").eq("user_id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Merchant not found for this user")

    return result.data["id"]
