import httpx
from backend.config import settings

ALLIUM_BASE = "https://api.allium.so/api/v1/explorer"


async def run_sql(sql: str) -> list[dict]:
    """Execute a SQL query against Allium and return rows as dicts."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{ALLIUM_BASE}/queries/run",
            headers={"X-API-KEY": settings.allium_api_key},
            json={"query": sql},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
