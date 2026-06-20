import aiosqlite
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


async def run_sql(sql: str) -> list[dict]:
    db = await get_db()
    async with db.execute(sql) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
