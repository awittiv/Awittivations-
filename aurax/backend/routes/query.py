from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.config import settings
from backend.services.claude_sql import nl_to_sql, explain_results

router = APIRouter(prefix="/query", tags=["NL Query"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    sql: str
    rows: list[dict]
    summary: str


async def _execute_sql(sql: str) -> list[dict]:
    """Route SQL to local Postgres or Allium depending on config."""
    if settings.use_local_db:
        from backend.services.db import run_sql
        return await run_sql(sql)
    from backend.services.allium import run_sql
    return await run_sql(sql)


@router.post("/", response_model=QueryResponse)
async def natural_language_query(req: QueryRequest):
    """
    Accept a plain-English DeFi question, convert to SQL via Claude,
    execute against local Postgres or Allium, return results + AI summary.

    Public endpoint — no API key required; abuse is bounded by the global
    per-IP rate limit (see ``Limiter`` in ``backend.main``).
    """
    try:
        sql = await nl_to_sql(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL generation failed: {e}")

    try:
        rows = await _execute_sql(sql)
    except Exception as e:
        backend = "local DB" if settings.use_local_db else "Allium"
        raise HTTPException(status_code=502, detail=f"{backend} query failed: {e}")

    summary = await explain_results(req.question, sql, rows[:5])

    return QueryResponse(question=req.question, sql=sql, rows=rows, summary=summary)
