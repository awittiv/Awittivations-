"""
Merges live Aave rates (chain RPC) with TVL/prices (DeFiLlama + CoinGecko)
then upserts into local SQLite. Both sources are free — no API key required.
DeFiLlama is called once for all chains to avoid concurrent request issues.
"""
import asyncio
from datetime import datetime, timezone

from backend.services.aave_rpc import _fetch_rates_sync
from backend.services.defillama import _fetch_pools, _fetch_prices, _pool_to_row, CHAIN_CONFIG
from backend.services.db import get_db

CHAINS = ["polygon", "arbitrum"]


async def refresh_reserves() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Fetch DeFiLlama pools for each chain and prices — all async, concurrent
    poly_pools, arb_pools = await asyncio.gather(
        _fetch_pools("Polygon"),
        _fetch_pools("Arbitrum"),
    )
    all_symbols = list({
        p.get("symbol", "").upper()
        for p in poly_pools + arb_pools
    })
    prices = await _fetch_prices(all_symbols)

    # Fetch on-chain rates synchronously (avoids async provider issues)
    loop = asyncio.get_event_loop()
    poly_rates, arb_rates = await asyncio.gather(
        loop.run_in_executor(None, _fetch_rates_sync, "polygon"),
        loop.run_in_executor(None, _fetch_rates_sync, "arbitrum"),
    )

    chain_data = [
        ("polygon",  poly_pools, poly_rates),
        ("arbitrum", arb_pools,  arb_rates),
    ]

    all_rows: list[dict] = []
    for chain, pools, rates in chain_data:
        cfg = CHAIN_CONFIG[chain]
        seen: dict[str, dict] = {}
        for pool in pools:
            row = _pool_to_row(pool, prices, chain, cfg["symbol_to_reserve"])
            if not row:
                continue
            rid = row["reserve_id"]
            if rid not in seen or row["tvl_usd"] > seen[rid]["tvl_usd"]:
                # Patch in live rates from RPC
                rpc = rates.get(rid.lower())
                if rpc:
                    row["liquidity_rate"]       = rpc["liquidity_rate"]
                    row["variable_borrow_rate"] = rpc["variable_borrow_rate"]
                    row["stable_borrow_rate"]   = rpc["stable_borrow_rate"]
                row["updated_at"] = now
                seen[rid] = row
        all_rows.extend(seen.values())

    if not all_rows:
        return 0

    db = await get_db()
    for r in all_rows:
        await db.execute(
            """
            INSERT INTO reserves (
                reserve_id, chain, symbol, name, decimals,
                liquidity_rate, variable_borrow_rate, stable_borrow_rate,
                utilization_rate, total_atoken_supply, total_variable_debt,
                total_stable_debt, price_usd, tvl_usd,
                is_active, is_frozen, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(reserve_id, chain) DO UPDATE SET
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
                r["reserve_id"], r["chain"], r["symbol"], r["name"], r["decimals"],
                r["liquidity_rate"], r["variable_borrow_rate"], r["stable_borrow_rate"],
                r["utilization_rate"], r["total_atoken_supply"], r["total_variable_debt"],
                r["total_stable_debt"], r["price_usd"], r["tvl_usd"],
                r["is_active"], r["is_frozen"], r["updated_at"],
            ],
        )
        await db.execute(
            """
            INSERT INTO reserve_history
                (reserve_id, chain, symbol, liquidity_rate, variable_borrow_rate,
                 utilization_rate, tvl_usd, snapshot_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                r["reserve_id"], r["chain"], r["symbol"],
                r["liquidity_rate"], r["variable_borrow_rate"],
                r["utilization_rate"], r["tvl_usd"], now,
            ],
        )

    await db.commit()
    return len(all_rows)
