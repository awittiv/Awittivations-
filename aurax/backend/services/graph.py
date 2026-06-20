import httpx
from backend.config import settings

GRAPH_BASE = "https://gateway.thegraph.com/api"

RESERVES_QUERY = """
{
  reserves(first: 50, where: { isActive: true }) {
    id
    symbol
    name
    decimals
    liquidityRate
    variableBorrowRate
    stableBorrowRate
    utilizationRate
    totalATokenSupply
    totalCurrentVariableDebt
    totalPrincipalStableDebt
    price { priceInEth }
    isFrozen
    isActive
  }
}
"""


async def fetch_reserves() -> list[dict]:
    """Pull live Aave v3 Polygon reserve data from The Graph."""
    url = f"{GRAPH_BASE}/{settings.graph_api_key}/subgraphs/id/{settings.aave_subgraph_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json={"query": RESERVES_QUERY})
        resp.raise_for_status()
        return resp.json()["data"]["reserves"]


def ray_to_pct(ray_value: str | float) -> float:
    """Convert Aave ray-unit rate to human-readable APY percentage."""
    return float(ray_value) / 1e25
