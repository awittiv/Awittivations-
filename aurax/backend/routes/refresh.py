from fastapi import APIRouter, Depends, HTTPException
from backend.auth import require_api_key
from backend.services.data_refresh import refresh_reserves

router = APIRouter(prefix="/refresh", tags=["Data"])


@router.post("/", dependencies=[Depends(require_api_key)])
async def trigger_refresh():
    """Manually trigger a live Aave data refresh from DeFiLlama."""
    try:
        count = await refresh_reserves()
        return {"updated": count, "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {e}")
