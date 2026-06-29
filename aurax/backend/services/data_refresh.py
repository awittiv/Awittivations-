"""
Refreshes Aave reserves from on-chain RPC (rates) enriched with DeFiLlama
TVL/utilization and CoinGecko prices, then upserts into local SQLite. All
sources are free — no API key required.

The RPC reserve list is authoritative: it returns live rates for *every*
active reserve we track, so iteration is driven by ``symbol_to_reserve`` (the
reserves we can label) rather than by DeFiLlama's pool list. DeFiLlama only
surfaces a subset of pools, so gating on it left untracked reserves (e.g.
USDT, WMATIC) frozen at seed values forever. TVL/utilization are enriched from
DeFiLlama where available and otherwise preserved via COALESCE in the upsert.
"""
import asyncio
from datetime import datetime, timezone

from backend.services.aave_rpc import _fetch_rates_sync
from backend.services.defillama import (
    _fetch_pools, _fetch_prices, _pool_to_row, CHAIN_CONFIG,
    SYMBOL_TO_NAME, SYMBOL_TO_DECIMALS,
)
from backend.services.db import get_db

CHAINS = ["polygon", "arbitrum"]


async def refresh_reserves() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # On-chain rates first — only the reserves we track, so it's a handful of
    # RPC calls per chain rather than one for every reserve in the pool.
    poly_targets = list(CHAIN_CONFIG["polygon"]["symbol_to_reserve"].values())
    arb_targets = list(CHAIN_CONFIG["arbitrum"]["symbol_to_reserve"].values())
    loop = asyncio.get_event_loop()
    poly_rates, arb_rates = await asyncio.gather(
        loop.run_in_executor(None, _fetch_rates_sync, "polygon", poly_targets),
        loop.run_in_executor(None, _fetch_rates_sync, "arbitrum", arb_targets),
    )

    # DeFiLlama pools + CoinGecko prices — enrichment (TVL, utilization, price).
    poly_pools, arb_pools = await asyncio.gather(
        _fetch_pools("Polygon"),
        _fetch_pools("Arbitrum"),
    )
    # Price every symbol we track, not just those DeFiLlama surfaces.
    all_symbols = {p.get("symbol", "").upper() for p in poly_pools + arb_pools}
    for chain in CHAINS:
        all_symbols.update(CHAIN_CONFIG[chain]["symbol_to_reserve"].keys())
    prices = await _fetch_prices(list(all_symbols))

    chain_data = [
        ("polygon",  poly_pools, poly_rates),
        ("arbitrum", arb_pools,  arb_rates),
    ]

    all_rows: list[dict] = []
    for chain, pools, rates in chain_data:
        cfg = CHAIN_CONFIG[chain]

        # DeFiLlama enrichment keyed by reserve_id (keep the highest-TVL pool).
        llama_by_rid: dict[str, dict] = {}
        for pool in pools:
            row = _pool_to_row(pool, prices, chain, cfg["symbol_to_reserve"])
            if not row:
                continue
            rid = row["reserve_id"]
            if rid not in llama_by_rid or row["tvl_usd"] > llama_by_rid[rid]["tvl_usd"]:
                llama_by_rid[rid] = row

        # Iterate over reserves we can label; RPC supplies live rates for all.
        for symbol, reserve_id in cfg["symbol_to_reserve"].items():
            rpc = rates.get(reserve_id.lower())
            llama = llama_by_rid.get(reserve_id)
            if not rpc and not llama:
                continue  # no live data for this reserve this cycle — skip

            row = {
                "chain":      chain,
                "reserve_id": reserve_id,
                "symbol":     symbol,
                "name":       SYMBOL_TO_NAME.get(symbol, symbol),
                "decimals":   SYMBOL_TO_DECIMALS.get(symbol, 18),
                "price_usd":  prices.get(symbol, (llama or {}).get("price_usd", 1.0)),
                "is_active":  1,
                "is_frozen":  0,
                "updated_at": now,
            }
            # Rates: prefer live on-chain RPC, fall back to DeFiLlama-derived.
            rate_src = rpc or llama
            row["liquidity_rate"]       = rate_src["liquidity_rate"]
            row["variable_borrow_rate"] = rate_src["variable_borrow_rate"]
            row["stable_borrow_rate"]   = rate_src["stable_borrow_rate"]

            # Utilization + supply/debt: prefer on-chain truth (RPC reads the
            # aToken/debt-token total supplies — DeFiLlama's pool feed has no
            # borrow figures, so its utilization was always 0). Fall back to
            # DeFiLlama, else None so the upsert COALESCEs to the prior value.
            if rpc and "utilization_rate" in rpc:
                scale = 10 ** SYMBOL_TO_DECIMALS.get(symbol, 18)
                row["utilization_rate"]    = rpc["utilization_rate"]
                row["total_atoken_supply"] = rpc["atoken_supply_raw"] / scale
                row["total_variable_debt"] = rpc["variable_debt_raw"] / scale
                row["total_stable_debt"]   = rpc["stable_debt_raw"] / scale
            elif llama:
                row["utilization_rate"]    = llama["utilization_rate"]
                row["total_atoken_supply"] = llama["total_atoken_supply"]
                row["total_variable_debt"] = llama["total_variable_debt"]
                row["total_stable_debt"]   = llama["total_stable_debt"]
            else:
                row["utilization_rate"]    = None
                row["total_atoken_supply"] = None
                row["total_variable_debt"] = None
                row["total_stable_debt"]   = None

            # TVL needs USD pricing, which only DeFiLlama provides.
            row["tvl_usd"] = llama["tvl_usd"] if llama else None
            all_rows.append(row)

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
                -- TVL/utilization come only from DeFiLlama; when this cycle had
                -- no DeFiLlama data for the reserve (excluded.* is NULL), keep
                -- the prior value rather than wiping it.
                utilization_rate     = COALESCE(excluded.utilization_rate, reserves.utilization_rate),
                total_atoken_supply  = COALESCE(excluded.total_atoken_supply, reserves.total_atoken_supply),
                total_variable_debt  = COALESCE(excluded.total_variable_debt, reserves.total_variable_debt),
                total_stable_debt    = COALESCE(excluded.total_stable_debt, reserves.total_stable_debt),
                price_usd            = excluded.price_usd,
                tvl_usd              = COALESCE(excluded.tvl_usd, reserves.tvl_usd),
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
