from fastapi import APIRouter, Query
from backend.config import settings
from backend.services.db import run_sql as db_run_sql
from backend.services.graph import fetch_reserves, ray_to_pct

router = APIRouter(prefix="/yields", tags=["Yields"])

RAY = 1e25

_LOCAL_YIELDS_SQL = """
SELECT
    reserve_id, symbol, name, decimals,
    liquidity_rate / {ray} AS deposit_apy_pct,
    variable_borrow_rate / {ray} AS variable_borrow_apy_pct,
    stable_borrow_rate / {ray} AS stable_borrow_apy_pct,
    utilization_rate,
    tvl_usd,
    is_frozen,
    is_active
FROM reserves
WHERE is_active = 1
ORDER BY deposit_apy_pct DESC
""".format(ray=RAY)


async def _get_reserves() -> list[dict]:
    if settings.use_local_db:
        return await db_run_sql(_LOCAL_YIELDS_SQL)
    raw = await fetch_reserves()
    return [_format_graph_reserve(r) for r in raw]


@router.get("/")
async def get_all_yields():
    return await _get_reserves()


@router.get("/top")
async def get_top_yields(
    min_tvl_usd: float = Query(default=1_000_000),
    limit: int = Query(default=10, le=50),
):
    reserves = await _get_reserves()
    filtered = [r for r in reserves if (r.get("tvl_usd") or 0) >= min_tvl_usd]
    filtered.sort(key=lambda r: r["deposit_apy_pct"], reverse=True)
    return filtered[:limit]


@router.get("/risk-adjusted")
async def get_risk_adjusted_yields(
    max_utilization: float = Query(default=0.85),
):
    reserves = await _get_reserves()
    safe = [
        r for r in reserves
        if r["utilization_rate"] <= max_utilization and not r["is_frozen"]
    ]
    safe.sort(key=lambda r: r["deposit_apy_pct"], reverse=True)
    return safe


def _format_graph_reserve(r: dict) -> dict:
    return {
        "reserve_id": r["id"],
        "symbol": r["symbol"],
        "name": r["name"],
        "decimals": r["decimals"],
        "deposit_apy_pct": round(ray_to_pct(r["liquidityRate"]), 4),
        "variable_borrow_apy_pct": round(ray_to_pct(r["variableBorrowRate"]), 4),
        "stable_borrow_apy_pct": round(ray_to_pct(r["stableBorrowRate"]), 4),
        "utilization_rate": round(float(r["utilizationRate"]), 4),
        "tvl_usd": float(r["totalATokenSupply"]),
        "is_frozen": r["isFrozen"],
        "is_active": r["isActive"],
    }
