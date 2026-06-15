import os
import hashlib
import uuid
import logging
from datetime import datetime, timezone

from supabase import create_client

from models.grant import CreateGrantRequest, GrantResponse, GrantStatus
from models.organization import get_entity
from models.project import ProjectName

logger = logging.getLogger(__name__)

_supabase = None

TABLE = "rails_grants"


def _db():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            logger.warning("[Rails] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        _supabase = create_client(url, key)
    return _supabase


def compute_compliance_hash(
    grant_id: str,
    project_name: str,
    program: str,
    amount_cents: int,
    ref: str,
) -> str:
    payload = f"{grant_id}:{project_name}:{program}:{amount_cents}:{ref}"
    return "0x" + hashlib.sha256(payload.encode()).hexdigest()


def project_id_hex(project_name: str) -> str:
    raw = hashlib.sha256(project_name.encode()).hexdigest()
    return "0x" + raw


async def create_grant(req: CreateGrantRequest) -> GrantResponse:
    grant_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    compliance_hash = compute_compliance_hash(
        grant_id,
        req.project_name,
        req.sba_program,
        req.amount_usd_cents,
        req.application_ref or "",
    )

    row = {
        "id":                grant_id,
        "project_name":      req.project_name,
        "sba_program":       req.sba_program,
        "amount_usd_cents":  req.amount_usd_cents,
        "description":       req.description,
        "nsfi_pillars":      req.nsfi_pillars,
        "application_ref":   req.application_ref,
        "beneficiary_wallet": req.beneficiary_wallet,
        "status":            "pending",
        "compliance_hash":   compliance_hash,
        "grant_id_onchain":  None,
        "attestation_tx":    None,
        "commitment_tx":     None,
        "claim_tx":          None,
        "created_at":        now,
        "updated_at":        now,
    }

    _db().table(TABLE).insert(row).execute()
    return GrantResponse(**row, entity=get_entity())


async def get_grants(project_name: ProjectName | None = None) -> list[GrantResponse]:
    query = _db().table(TABLE).select("*")
    if project_name:
        query = query.eq("project_name", project_name)
    result = query.order("created_at", desc=True).execute()
    return [GrantResponse(**r) for r in result.data]


async def get_grant(grant_id: str) -> GrantResponse | None:
    result = _db().table(TABLE).select("*").eq("id", grant_id).maybe_single().execute()
    if not result.data:
        return None
    return GrantResponse(**result.data)


async def update_grant(grant_id: str, status: GrantStatus, **fields) -> None:
    updates = {
        "status":     status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    _db().table(TABLE).update(updates).eq("id", grant_id).execute()
