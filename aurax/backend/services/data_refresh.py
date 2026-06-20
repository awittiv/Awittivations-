"""
Merges live Aave rates (Polygon RPC) with TVL/prices (DeFiLlama + CoinGecko)
then upserts into local SQLite. Both sources are free — no API key required.
"""
import asyncio
from datetime import datetime, timezone

from backend.services.aave_rpc import fetch_aave_rates
from backend.services.defillama import fetch_live_reserves
from backend.services.db import get_db

RAY = 1e25


async def refresh_reserves() -> int:
    # Run both fetches concurrently
    rates_task = asyncio.create_task(fetch_aave_rates())
    llama_task = asyncio.create_task(fetch_live_reserves())
    rates, llama_rows = await asyncio.gather(rates_task, llama_task)

    # Merge: start from DeFiLlama rows (TVL/prices), patch rates from RPC
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    merged: list[dict] = []

    for row in llama_rows:
        addr = row["reserve_id"].lower()
        rpc = rates.get(addr)
        if rpc:
            row["liquidity_rate"]       = rpc["liquidity_rate"]
            row["variable_borrow_rate"] = rpc["variable_borrow_rate"]
            row["stable_borrow_rate"]   = rpc["stable_borrow_rate"]
        row["updated_at"] = now
        merged.append(row)

    if not merged:
        return 0

    db = await get_db()
    for r in merged:
        await db.execute(
            """
            INSERT INTO reserves (
                reserve_id, symbol, name, decimals,
                liquidity_rate, variable_borrow_rate, stable_borrow_rate,
                utilization_rate, total_atoken_supply, total_variable_debt,
                total_stable_debt, price_usd, tvl_usd,
                is_active, is_frozen, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(reserve_id) DO UPDATE SET
                liquidity_rate       = excluded.liquidity_rate,
                variable_borrow_rate = excluded.variable_borrow_rate,
                stable_borrow_rate   = excluded.stable_borrow_rate,
                utilization_rate     = excluded.utilization_rate,
                total_atoken_supply  = excluded.total_atoken_supply,
                total_variable_debt  = excluded.total_variable_debt,
                total_stable_debt    = excluded.total_stable_debt,
                price_usd            = excluded.price_usd,
                tvl_usd              = excluded.tvl_usd,
                updated_at           = excluded.updated_at
            """,
            [
                r["reserve_id"], r["symbol"], r["name"], r["decimals"],
                r["liquidity_rate"], r["variable_borrow_rate"], r["stable_borrow_rate"],
                r["utilization_rate"], r["total_atoken_supply"], r["total_variable_debt"],
                r["total_stable_debt"], r["price_usd"], r["tvl_usd"],
                r["is_active"], r["is_frozen"], r["updated_at"],
            ],
        )
        await db.execute(
            """
            INSERT INTO reserve_history
                (reserve_id, symbol, liquidity_rate, variable_borrow_rate,
                 utilization_rate, tvl_usd, snapshot_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            [
                r["reserve_id"], r["symbol"],
                r["liquidity_rate"], r["variable_borrow_rate"],
                r["utilization_rate"], r["tvl_usd"], now,
            ],
        )

    await db.commit()
    return len(merged)
