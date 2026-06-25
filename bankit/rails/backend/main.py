# ruff: noqa: E402  — load_dotenv() must run before importing env-reading modules
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import grants, nsfi, disbursement

app = FastAPI(
    title="Bankit Rails API",
    version="1.0.0",
    description=(
        "Non-custodial banking rails for RBI NSFI 2025-30 and SBA grant funding. "
        "Platform never possesses funds. All disbursements are atomic and on-chain."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://launchlayer.app",
        os.getenv("FRONTEND_URL", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(grants.router)
app.include_router(nsfi.router)
app.include_router(disbursement.router)


@app.get("/health")
async def health():
    return {
        "status":          "ok",
        "service":         "bankit-rails",
        "non_custodial":   True,
        "frameworks":      ["NSFI-2025-30", "SBA"],
        "chain":           "Polygon Amoy (testnet) → Polygon Mainnet",
        "contracts": {
            "RailsVault":            os.getenv("RAILS_VAULT_ADDRESS", "not deployed"),
            "AtomicDisbursement":    os.getenv("ATOMIC_DISBURSEMENT_ADDRESS", "not deployed"),
            "ComplianceAttestation": os.getenv("COMPLIANCE_ATTESTATION_ADDRESS", "not deployed"),
        },
    }
