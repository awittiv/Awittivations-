from fastapi import APIRouter, HTTPException
from models.grant import CreateGrantRequest, GrantResponse, AttestGrantRequest, RejectGrantRequest
from models.organization import get_entity
from models.project import ProjectName, PROGRAM_TYPE_ID, NSFI_PILLAR_ID
from services import sba_service, atomic_settlement

router = APIRouter(prefix="/grants", tags=["grants"])


@router.post("/", response_model=GrantResponse, status_code=201)
async def create_grant(req: CreateGrantRequest):
    return await sba_service.create_grant(req)


@router.get("/", response_model=list[GrantResponse])
async def list_grants(project: ProjectName | None = None):
    return await sba_service.get_grants(project)


@router.get("/{grant_id}", response_model=GrantResponse)
async def get_grant(grant_id: str):
    grant = await sba_service.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    return grant


@router.post("/{grant_id}/attest")
async def attest_grant(grant_id: str, req: AttestGrantRequest):
    """
    Write compliance attestation on-chain after SBA or NSFI approval is confirmed.
    This gates the beneficiary's ability to claim funds from AtomicDisbursement.
    """
    grant = await sba_service.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    if grant.status != "pending":
        raise HTTPException(400, f"Expected status=pending, got {grant.status}")

    p_id_hex     = sba_service.project_id_hex(grant.project_name)
    program_type = PROGRAM_TYPE_ID[grant.sba_program]
    nsfi_pillar  = NSFI_PILLAR_ID.get(req.primary_nsfi_pillar or "", 0) if req.primary_nsfi_pillar else 0

    tx = await atomic_settlement.write_compliance_attestation(
        compliance_hash_hex = grant.compliance_hash or "",
        project_id_hex      = p_id_hex,
        program_type        = program_type,
        nsfi_pillar         = nsfi_pillar,
        application_ref     = req.application_ref,
        amount_usd_cents    = grant.amount_usd_cents,
    )

    if not tx:
        raise HTTPException(502, "On-chain attestation failed — check node connectivity and env vars")

    await sba_service.update_grant(grant_id, "attested",
        attestation_tx=tx,
        application_ref=req.application_ref,
    )
    return {"status": "attested", "tx_hash": tx, "compliance_hash": grant.compliance_hash}


@router.post("/{grant_id}/reject")
async def reject_grant(grant_id: str, req: RejectGrantRequest):
    grant = await sba_service.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    if grant.status not in ("pending", "attested"):
        raise HTTPException(400, f"Cannot reject grant in status={grant.status}")

    if grant.status == "attested" and grant.compliance_hash:
        await atomic_settlement.revoke_attestation(grant.compliance_hash)

    await sba_service.update_grant(grant_id, "rejected", rejection_reason=req.reason)
    return {"status": "rejected"}


@router.get("/entity")
async def get_entity_info():
    """Awittivations LLC federal identifiers — UEI, DUNS, EIN for SBA submissions."""
    return get_entity()


@router.get("/{grant_id}/compliance")
async def check_compliance(grant_id: str):
    grant = await sba_service.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")
    attested = await atomic_settlement.is_attested(grant.compliance_hash or "")
    return {
        "grant_id":          grant_id,
        "project":           grant.project_name,
        "compliance_hash":   grant.compliance_hash,
        "on_chain_attested": attested,
        "db_status":         grant.status,
    }
