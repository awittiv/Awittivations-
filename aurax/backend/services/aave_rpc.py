"""
Live Aave v3 rates via direct chain RPC — no API key, no cost.
Uses sync web3 in a thread executor to avoid async provider issues.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3

POOL_ADDR = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"

# Multiple free endpoints per chain — public nodes are flaky, so we fail fast
# (short timeout) and fall back to the next one rather than hanging.
CHAINS = {
    "polygon": [
        "https://polygon-bor-rpc.publicnode.com",
        "https://polygon-rpc.com",
        "https://rpc.ankr.com/polygon",
    ],
    "arbitrum": [
        "https://arbitrum-one-rpc.publicnode.com",
        "https://arb1.arbitrum.io/rpc",
        "https://rpc.ankr.com/arbitrum",
    ],
}

_RPC_TIMEOUT = 8

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

# Minimal ERC20 — aToken/debt-token total supplies give real utilization.
_ERC20_ABI = [
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"type": "uint256", "name": ""}],
        "stateMutability": "view",
        "type": "function",
    }
]


def _fetch_rates_sync(chain: str, addresses: list[str] | None = None) -> dict[str, dict]:
    """Fetch live Aave reserve rates keyed by lowercase asset address.

    When ``addresses`` is given, only those reserves are queried (one RPC
    round-trip each) instead of every reserve from getReservesList — far fewer
    calls against a slow public node. Tries each endpoint in turn so one dead
    node doesn't sink the refresh.
    """
    last_error: Exception | None = None
    for rpc_url in CHAINS[chain]:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": _RPC_TIMEOUT}))
        pool = w3.eth.contract(
            address=Web3.to_checksum_address(POOL_ADDR.lower()),
            abi=_POOL_ABI,
        )
        try:
            targets = addresses if addresses else pool.functions.getReservesList().call()
        except Exception as e:  # endpoint unreachable — try the next one
            last_error = e
            continue

        def _total_supply(token_addr: str) -> float:
            erc20 = w3.eth.contract(
                address=Web3.to_checksum_address(token_addr), abi=_ERC20_ABI
            )
            return float(erc20.functions.totalSupply().call())

        rates: dict[str, dict] = {}
        for addr in targets:
            try:
                data = pool.functions.getReserveData(
                    Web3.to_checksum_address(addr)
                ).call()
                entry = {
                    "liquidity_rate":       float(data[2]),
                    "variable_borrow_rate": float(data[4]),
                    "stable_borrow_rate":   float(data[5]),
                }
                # data[8/9/10] = aToken / stableDebt / variableDebt addresses.
                # Their total supplies (raw, underlying decimals) give real
                # utilization = total debt / total supplied.
                try:
                    atoken = _total_supply(data[8])
                    stable_debt = _total_supply(data[9])
                    variable_debt = _total_supply(data[10])
                    total_debt = variable_debt + stable_debt
                    entry["atoken_supply_raw"] = atoken
                    entry["variable_debt_raw"] = variable_debt
                    entry["stable_debt_raw"] = stable_debt
                    entry["utilization_rate"] = round(total_debt / atoken, 4) if atoken > 0 else 0.0
                except Exception:
                    pass  # keep rates even if the supply reads fail
                rates[addr.lower()] = entry
            except Exception:
                pass  # skip a single unreadable reserve, keep the rest
        if rates:
            return rates
        last_error = last_error or RuntimeError(f"no rates from {rpc_url}")

    if last_error:
        raise last_error
    return {}


async def fetch_aave_rates(
    chain: str = "polygon", addresses: list[str] | None = None
) -> dict[str, dict]:
    """
    Returns live Aave rates keyed by lowercase asset address.
    Runs sync web3 in a thread so it doesn't block the event loop.
    """
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, _fetch_rates_sync, chain, addresses)
