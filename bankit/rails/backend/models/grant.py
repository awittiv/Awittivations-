from pydantic import BaseModel
from typing import Literal
from datetime import datetime
from models.project import ProjectName, SBAProgramType, NSFIPillar
from models.organization import AwittivationsEntity


GrantStatus = Literal[
    "pending",    # application submitted, awaiting SBA/NSFI approval
    "attested",   # compliance hash written on-chain, awaiting grantor commitment
    "committed",  # grantor locked funds in AtomicDisbursement contract
    "claimed",    # beneficiary claimed funds — disbursement complete
    "cancelled",  # grant cancelled, funds returned to grantor
    "rejected",   # SBA/NSFI application rejected
]


class CreateGrantRequest(BaseModel):
    project_name: ProjectName
    sba_program: SBAProgramType
    amount_usd_cents: int
    description: str
    nsfi_pillars: list[NSFIPillar] = []
    application_ref: str | None = None
    beneficiary_wallet: str
    deadline_days: int = 90


class GrantResponse(BaseModel):
    id: str
    project_name: ProjectName
    sba_program: SBAProgramType
    amount_usd_cents: int
    description: str
    nsfi_pillars: list[NSFIPillar]
    application_ref: str | None
    beneficiary_wallet: str
    status: GrantStatus
    compliance_hash: str | None
    grant_id_onchain: str | None
    attestation_tx: str | None
    commitment_tx: str | None
    claim_tx: str | None
    entity: AwittivationsEntity | None = None
    created_at: datetime
    updated_at: datetime


class AttestGrantRequest(BaseModel):
    application_ref: str
    primary_nsfi_pillar: NSFIPillar | None = None


class RejectGrantRequest(BaseModel):
    reason: str
