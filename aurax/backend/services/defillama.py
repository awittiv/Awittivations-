"""
Free Aave v3 Polygon data via DeFiLlama — no API key required.
"""
import httpx
from datetime import datetime, timezone

RAY = 1e25

SYMBOL_TO_RESERVE = {
    "USDC":   "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
    "WETH":   "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
    "WMATIC": "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270",
    "WBTC":   "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6",
    "DAI":    "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",
    "USDT":   "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
    "AAVE":   "0xd6df932a45c0f255f85145f286ea0b292b21c90b",
    "LINK":   "0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39",
}

SYMBOL_TO_NAME = {
    "USDC":   "USD Coin",
    "WETH":   "Wrapped Ether",
    "WMATIC": "Wrapped Matic",
    "WBTC":   "Wrapped Bitcoin",
    "DAI":    "Dai Stablecoin",
    "USDT":   "Tether USD",
    "AAVE":   "Aave Token",
    "LINK":   "ChainLink Token",
}

SYMBOL_TO_DECIMALS = {
    "USDC": 6, "WETH": 18, "WMATIC": 18, "WBTC": 8,
    "DAI": 18, "USDT": 6, "AAVE": 18, "LINK": 18,
}

COINGECKO_IDS = {
    "USDC":   "usd-coin",
    "WETH":   "ethereum",
    "WMATIC": "matic-network",
    "WBTC":   "wrapped-bitcoin",
    "DAI":    "dai",
    "USDT":   "tether",
    "AAVE":   "aave",
    "LINK":   "chainlink",
}


_HEADERS = {"Accept-Encoding": "gzip, deflate"}


async def _fetch_pools() -> list[dict]:
    async with httpx.AsyncClient(timeout=30, headers=_HEADERS) as client:
        resp = await client.get("https://yields.llama.fi/pools")
        resp.raise_for_status()
    return [
        p for p in resp.json()["data"]
        if p.get("project") == "aave-v3"
        and p.get("chain") == "Polygon"
        and p.get("poolMeta") != "stable"
    ]


async def _fetch_prices(symbols: list[str]) -> dict[str, float]:
    ids = ",".join(
        COINGECKO_IDS[s] for s in symbols if s in COINGECKO_IDS
    )
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
        resp = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
        )
        resp.raise_for_status()
    data = resp.json()
    return {
        sym: data[cg_id]["usd"]
        for sym, cg_id in COINGECKO_IDS.items()
        if cg_id in data
    }


def _pool_to_row(pool: dict, prices: dict) -> dict | None:
    symbol = pool.get("symbol", "").upper().strip()
    reserve_id = SYMBOL_TO_RESERVE.get(symbol)
    if not reserve_id:
        return None

    deposit_apy  = float(pool.get("apyBase") or 0)
    borrow_apy   = float(pool.get("apyBaseBorrow") or 0)
    tvl_usd      = float(pool.get("tvlUsd") or 0)
    supply_usd   = float(pool.get("totalSupplyUsd") or tvl_usd)
    borrow_usd   = float(pool.get("totalBorrowUsd") or 0)
    utilization  = round(borrow_usd / supply_usd, 4) if supply_usd > 0 else 0.0
    price_usd    = prices.get(symbol, 1.0)
    supply_tok   = supply_usd / price_usd if price_usd else 0.0
    debt_tok     = borrow_usd / price_usd if price_usd else 0.0

    return {
        "reserve_id":           reserve_id,
        "symbol":               symbol,
        "name":                 SYMBOL_TO_NAME.get(symbol, symbol),
        "decimals":             SYMBOL_TO_DECIMALS.get(symbol, 18),
        "liquidity_rate":       deposit_apy * RAY,
        "variable_borrow_rate": borrow_apy * RAY,
        "stable_borrow_rate":   borrow_apy * 1.3 * RAY,
        "utilization_rate":     utilization,
        "total_atoken_supply":  supply_tok,
        "total_variable_debt":  debt_tok * 0.9,
        "total_stable_debt":    debt_tok * 0.1,
        "price_usd":            price_usd,
        "tvl_usd":              tvl_usd,
        "is_active":            1,
        "is_frozen":            0,
        "updated_at":           datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


async def fetch_live_reserves() -> list[dict]:
    """Return live Aave v3 Polygon reserves from DeFiLlama + CoinGecko."""
    pools = await _fetch_pools()
    symbols = list({p.get("symbol", "").upper() for p in pools})
    prices = await _fetch_prices(symbols)

    seen: dict[str, dict] = {}
    for pool in pools:
        row = _pool_to_row(pool, prices)
        if row:
            rid = row["reserve_id"]
            if rid not in seen or row["tvl_usd"] > seen[rid]["tvl_usd"]:
                seen[rid] = row

    return list(seen.values())
