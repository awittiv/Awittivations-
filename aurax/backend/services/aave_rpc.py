"""
Live Aave v3 rates via direct chain RPC — no API key, no cost.
Uses sync web3 in a thread executor to avoid async provider issues.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3

POOL_ADDR = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"

CHAINS = {
    "polygon":  "https://polygon-bor-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-one-rpc.publicnode.com",
}

_POOL_ABI = [
    {
        "inputs": [],
        "name": "getReservesList",
        "outputs": [{"type": "address[]", "name": ""}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {
                "components": [
                    {"name": "configuration",              "type": "uint256"},
                    {"name": "liquidityIndex",             "type": "uint128"},
                    {"name": "currentLiquidityRate",       "type": "uint128"},
                    {"name": "variableBorrowIndex",        "type": "uint128"},
                    {"name": "currentVariableBorrowRate",  "type": "uint128"},
                    {"name": "currentStableBorrowRate",    "type": "uint128"},
                    {"name": "lastUpdateTimestamp",        "type": "uint40"},
                    {"name": "id",                         "type": "uint16"},
                    {"name": "aTokenAddress",              "type": "address"},
                    {"name": "stableDebtTokenAddress",     "type": "address"},
                    {"name": "variableDebtTokenAddress",   "type": "address"},
                    {"name": "interestRateStrategyAddress","type": "address"},
                    {"name": "accruedToTreasury",          "type": "uint128"},
                    {"name": "unbacked",                   "type": "uint128"},
                    {"name": "isolationModeTotalDebt",     "type": "uint128"},
                ],
                "type": "tuple",
                "name": "",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


def _fetch_rates_sync(chain: str) -> dict[str, dict]:
    rpc_url = CHAINS[chain]
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    pool = w3.eth.contract(
        address=Web3.to_checksum_address(POOL_ADDR.lower()),
        abi=_POOL_ABI,
    )
    reserves_list = pool.functions.getReservesList().call()
    rates: dict[str, dict] = {}
    for addr in reserves_list:
        try:
            data = pool.functions.getReserveData(addr).call()
            rates[addr.lower()] = {
                "liquidity_rate":       float(data[2]),
                "variable_borrow_rate": float(data[4]),
                "stable_borrow_rate":   float(data[5]),
            }
        except Exception:
            pass
    return rates


async def fetch_aave_rates(chain: str = "polygon") -> dict[str, dict]:
    """
    Returns live Aave rates keyed by lowercase asset address.
    Runs sync web3 in a thread so it doesn't block the event loop.
    """
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _fetch_rates_sync, chain)
