from pydantic import BaseModel
from models.project import ProjectName


class DisbursementStatus(BaseModel):
    grant_id: str
    project_name: ProjectName
    amount_usd_cents: int
    beneficiary_wallet: str
    compliance_attested: bool
    grant_committed: bool
    grant_claimed: bool
    is_cancelled: bool
    on_chain_grant_id: str | None
    compliance_hash: str | None


class ProjectSummary(BaseModel):
    project: str
    total_grants: int
    total_usd_cents: int
    pending: int
    attested: int
    committed: int
    claimed: int
    cancelled: int
    rejected: int
