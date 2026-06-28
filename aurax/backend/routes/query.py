from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.config import settings
from backend.ratelimit import limiter
from backend.services.claude_sql import nl_to_sql, repair_sql, explain_results

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
@limiter.limit("10/minute")
async def natural_language_query(request: Request, req: QueryRequest):
    """
    Accept a plain-English DeFi question, convert to SQL via Claude,
    execute against local Postgres or Allium, return results + AI summary.

    Public endpoint — no API key required. Because each call makes two
    Claude requests, it carries a tighter 10/min/IP cap than the global
    30/min default (see ``backend.ratelimit``).
    """
    try:
        sql = await nl_to_sql(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL generation failed: {e}")

    try:
        rows = await _execute_sql(sql)
    except Exception as first_error:
        # The NL->SQL step occasionally emits SQL the DB rejects. Feed the
        # error back to Claude for one repair attempt before giving up.
        try:
            sql = await repair_sql(req.question, sql, str(first_error))
            rows = await _execute_sql(sql)
        except Exception as second_error:
            backend = "local DB" if settings.use_local_db else "Allium"
            raise HTTPException(
                status_code=502,
                detail=f"{backend} query failed after repair attempt: {second_error}",
            )

    summary = await explain_results(req.question, sql, rows[:5])

    return QueryResponse(question=req.question, sql=sql, rows=rows, summary=summary)
