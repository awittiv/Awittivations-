import aiosqlite
from fastapi import HTTPException
from backend.config import settings

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.sqlite_path)
        _db.row_factory = aiosqlite.Row
    return _db


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def _validate_sql(sql: str) -> None:
    """Only allow SELECT statements — reject anything destructive."""
    stripped = sql.strip()
    first = stripped.split()[0].upper() if stripped else ""
    if first != "SELECT":
        raise HTTPException(status_code=400, detail=f"Only SELECT queries are allowed, got: {first}")


async def run_sql(sql: str) -> list[dict]:
    _validate_sql(sql)
    db = await get_db()
    async with db.execute(sql) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
