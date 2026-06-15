from fastapi import APIRouter, HTTPException
from models.disbursement import DisbursementStatus, ProjectSummary
from services import sba_service, atomic_settlement

router = APIRouter(prefix="/disbursement", tags=["disbursement"])


@router.get("/status/{grant_id}", response_model=DisbursementStatus)
async def disbursement_status(grant_id: str):
    """Live disbursement state — cross-references DB status with on-chain attestation."""
    grant = await sba_service.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Grant not found")

    attested = await atomic_settlement.is_attested(grant.compliance_hash or "")

    return DisbursementStatus(
        grant_id=grant_id,
        project_name=grant.project_name,
        amount_usd_cents=grant.amount_usd_cents,
        beneficiary_wallet=grant.beneficiary_wallet,
        compliance_attested=attested,
        grant_committed=grant.grant_id_onchain is not None,
        grant_claimed=grant.status == "claimed",
        is_cancelled=grant.status == "cancelled",
        on_chain_grant_id=grant.grant_id_onchain,
        compliance_hash=grant.compliance_hash,
    )


@router.get("/projects", response_model=list[ProjectSummary])
async def all_project_disbursements():
    """Aggregate disbursement summary across all Awittivations projects."""
    grants = await sba_service.get_grants()

    by_project: dict[str, dict] = {}
    for g in grants:
        p = g.project_name
        if p not in by_project:
            by_project[p] = {
                "project":        p,
                "total_grants":   0,
                "total_usd_cents": 0,
                "pending":        0,
                "attested":       0,
                "committed":      0,
                "claimed":        0,
                "cancelled":      0,
                "rejected":       0,
            }
        by_project[p]["total_grants"]    += 1
        by_project[p]["total_usd_cents"] += g.amount_usd_cents
        status_key = g.status
        by_project[p][status_key] = by_project[p].get(status_key, 0) + 1

    return list(by_project.values())
