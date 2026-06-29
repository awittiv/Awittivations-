from fastapi import APIRouter, Query
from backend.services.db import run_sql as db_run_sql

router = APIRouter(prefix="/yields", tags=["Yields"])

RAY = 1e25

_SQL = """
SELECT
    chain, reserve_id, symbol, name, decimals,
    liquidity_rate / {ray} AS deposit_apy_pct,
    variable_borrow_rate / {ray} AS variable_borrow_apy_pct,
    stable_borrow_rate / {ray} AS stable_borrow_apy_pct,
    utilization_rate,
    tvl_usd,
    is_frozen,
    is_active
FROM reserves
WHERE is_active = 1 {{chain_filter}}
ORDER BY deposit_apy_pct DESC
""".format(ray=RAY)


def _chain_filter(chain: str | None) -> str:
    if chain:
        return f"AND chain = '{chain}'"
    return ""


async def _get_reserves(chain: str | None = None) -> list[dict]:
    sql = _SQL.replace("{chain_filter}", _chain_filter(chain))
    return await db_run_sql(sql)


@router.get("/")
async def get_all_yields(chain: str | None = Query(default=None)):
    return await _get_reserves(chain)


@router.get("/top")
async def get_top_yields(
    chain: str | None = Query(default=None),
    min_tvl_usd: float = Query(default=1_000_000),
    limit: int = Query(default=10, le=50),
):
    reserves = await _get_reserves(chain)
    filtered = [r for r in reserves if (r.get("tvl_usd") or 0) >= min_tvl_usd]
    return filtered[:limit]


@router.get("/risk-adjusted")
async def get_risk_adjusted_yields(
    chain: str | None = Query(default=None),
    max_utilization: float = Query(default=0.85),
):
    reserves = await _get_reserves(chain)
    return [
        r for r in reserves
        # utilization_rate is NULL for reserves DeFiLlama doesn't enrich; we
        # can't assert those are under the threshold, so leave them out rather
        # than crash on a None comparison.
        if r["utilization_rate"] is not None
        and r["utilization_rate"] <= max_utilization
        and not r["is_frozen"]
    ]
