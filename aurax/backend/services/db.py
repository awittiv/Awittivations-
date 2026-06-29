import shutil
import sqlite3
from pathlib import Path

import aiosqlite
from fastapi import HTTPException
from backend.config import settings

_db: aiosqlite.Connection | None = None


def ensure_db_initialized() -> None:
    """Make sure the DB file and schema exist before first use.

    On a fresh persistent volume the DB path is empty. Prefer copying the
    image-bundled DB (preserves bootstrap/seed data); otherwise create the
    schema from scratch. A no-op once the volume already holds the DB, so
    data accumulated on the volume survives deploys.
    """
    target = Path(settings.sqlite_path)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)

    bundled = Path(__file__).resolve().parents[2] / "aurax.db"
    if bundled.exists() and bundled.resolve() != target.resolve():
        shutil.copy(bundled, target)
        return

    schema = (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text()
    con = sqlite3.connect(target)
    try:
        con.executescript(schema)
        con.commit()
    finally:
        con.close()


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
