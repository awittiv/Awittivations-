import os
import hmac
import hashlib
import asyncio
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()

WEBHOOK_SECRET = os.environ.get("LINKEDIN_WEBHOOK_SECRET", "")


def _verify_signature(secret: str, body: bytes, signature: str) -> bool:
    if not secret:
        return True  # skip verification in dev when secret not set
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class ConnectionPayload(BaseModel):
    linkedin_url: str
    name: str
    email: str | None = None
    company: str | None = None
    industry: str | None = None
    role: str | None = None


async def _run_sales_crew(payload: ConnectionPayload):
    """Runs the sales crew in the background after a connection is accepted."""
    import sys
    sys.path.insert(0, "/home/jack/Banking/crew.ai/outreach")

    os.environ.setdefault("LEAD_LINKEDIN_URL", payload.linkedin_url)
    os.environ.setdefault("LEAD_EMAIL", payload.email or "")

    from sales_crew import sales_crew
    await asyncio.to_thread(
        sales_crew.kickoff,
        inputs={
            "linkedin_url": payload.linkedin_url,
            "email": payload.email or "",
            "name": payload.name,
            "company": payload.company or "",
            "industry": payload.industry or "",
            "role": payload.role or "",
        },
    )


@router.post("/webhook/linkedin/connection-accepted")
async def linkedin_connection_accepted(
    request: Request,
    background_tasks: BackgroundTasks,
):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if WEBHOOK_SECRET and not _verify_signature(WEBHOOK_SECRET, body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    data = await request.json()
    payload = ConnectionPayload(**data)

    background_tasks.add_task(_run_sales_crew, payload)

    return {
        "status": "accepted",
        "message": f"Sales crew triggered for {payload.name}",
    }
