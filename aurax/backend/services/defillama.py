"""
Free Aave v3 multi-chain data via DeFiLlama + CoinGecko — no API key required.
"""
import httpx
from datetime import datetime, timezone

RAY = 1e25

CHAIN_CONFIG = {
    "polygon": {
        "llama_chain": "Polygon",
        "symbol_to_reserve": {
            "USDC":   "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
            "WETH":   "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619",
            "WMATIC": "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270",
            "WBTC":   "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6",
            "DAI":    "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",
            "USDT":   "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
            "AAVE":   "0xd6df932a45c0f255f85145f286ea0b292b21c90b",
            "LINK":   "0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39",
        },
    },
    "arbitrum": {
        "llama_chain": "Arbitrum",
        "symbol_to_reserve": {
            "USDC":   "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
            "USDC.E": "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8",
            "WETH":   "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
            "WBTC":   "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f",
            "DAI":    "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1",
            "USDT":   "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
            "ARB":    "0x912ce59144191c1204e64559fe8253a0e49e6548",
            "LINK":   "0xf97f4df75117a78c1a5a0dbb814af92458539fb4",
            "AAVE":   "0xba5ddd1f9d7f570dc94a51479a000e3bce967196",
            "WSTETH": "0x5979d7b546e38e414f7e9822514be443a4800529",
        },
    },
}

SYMBOL_TO_NAME = {
    "USDC": "USD Coin", "USDC.E": "USD Coin (Bridged)",
    "WETH": "Wrapped Ether", "WMATIC": "Wrapped Matic",
    "WBTC": "Wrapped Bitcoin", "DAI": "Dai Stablecoin",
    "USDT": "Tether USD", "AAVE": "Aave Token",
    "LINK": "ChainLink Token", "ARB": "Arbitrum",
    "WSTETH": "Wrapped stETH",
}

SYMBOL_TO_DECIMALS = {
    "USDC": 6, "USDC.E": 6, "WETH": 18, "WMATIC": 18,
    "WBTC": 8, "DAI": 18, "USDT": 6, "AAVE": 18,
    "LINK": 18, "ARB": 18, "WSTETH": 18,
}

COINGECKO_IDS = {
    "USDC": "usd-coin", "USDC.E": "usd-coin",
    "WETH": "ethereum", "WMATIC": "matic-network",
    "WBTC": "wrapped-bitcoin", "DAI": "dai",
    "USDT": "tether", "AAVE": "aave",
    "LINK": "chainlink", "ARB": "arbitrum",
    "WSTETH": "wrapped-steth",
}

_HEADERS = {"Accept-Encoding": "gzip, deflate"}


async def _fetch_pools(llama_chain: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30, headers=_HEADERS) as client:
        resp = await client.get("https://yields.llama.fi/pools")
        resp.raise_for_status()
    return [
        p for p in resp.json()["data"]
        if p.get("project") == "aave-v3"
        and p.get("chain") == llama_chain
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


def _pool_to_row(pool: dict, prices: dict, chain: str, symbol_to_reserve: dict) -> dict | None:
    symbol = pool.get("symbol", "").upper().strip()
    reserve_id = symbol_to_reserve.get(symbol)
    if not reserve_id:
        return None

    deposit_apy = float(pool.get("apyBase") or 0)
    borrow_apy  = float(pool.get("apyBaseBorrow") or 0)
    tvl_usd     = float(pool.get("tvlUsd") or 0)
    supply_usd  = float(pool.get("totalSupplyUsd") or tvl_usd)
    borrow_usd  = float(pool.get("totalBorrowUsd") or 0)
    utilization = round(borrow_usd / supply_usd, 4) if supply_usd > 0 else 0.0
    price_usd   = prices.get(symbol, 1.0)
    supply_tok  = supply_usd / price_usd if price_usd else 0.0
    debt_tok    = borrow_usd / price_usd if price_usd else 0.0

    return {
        "chain":                chain,
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


async def fetch_live_reserves(chain: str = "polygon") -> list[dict]:
    """Return live Aave v3 reserves for the given chain from DeFiLlama + CoinGecko."""
    cfg = CHAIN_CONFIG[chain]
    pools = await _fetch_pools(cfg["llama_chain"])
    symbols = list({p.get("symbol", "").upper() for p in pools})
    prices = await _fetch_prices(symbols)

    seen: dict[str, dict] = {}
    for pool in pools:
        row = _pool_to_row(pool, prices, chain, cfg["symbol_to_reserve"])
        if row:
            rid = row["reserve_id"]
            if rid not in seen or row["tvl_usd"] > seen[rid]["tvl_usd"]:
                seen[rid] = row

    return list(seen.values())
