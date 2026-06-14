"""
Module: api_gateway.py
Description: FastAPI REST gateway exposing the TPAP intelligence engine
             for cross-border corridor routing directives.
             Strictly non-custodial — routes data and cryptographic instructions only.
"""

import os
import datetime
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from credit_passport_engine import AutonomousOrchestrationEngine, TransactionContext
from payload_validator import AutonomousPayloadValidator, DirectiveValidationError

app = FastAPI(
    title="TPAP Intelligence Gateway",
    version="1.0.0",
    description="Non-custodial cross-border intelligence routing layer — Awittivations / Bankit",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons — initialized once on first use
_orchestrator: AutonomousOrchestrationEngine | None = None
_validator: AutonomousPayloadValidator | None = None


def get_orchestrator() -> AutonomousOrchestrationEngine:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AutonomousOrchestrationEngine()
    return _orchestrator


def get_validator() -> AutonomousPayloadValidator:
    global _validator
    if _validator is None:
        _validator = AutonomousPayloadValidator()
    return _validator


# --- Auth ---

GATEWAY_TOKEN = os.getenv("GATEWAY_API_TOKEN", "")


async def verify_token(authorization: str = Header(...)):
    if not GATEWAY_TOKEN:
        return  # Dev mode: no token configured
    token = authorization.removeprefix("Bearer ").strip()
    if not authorization.startswith("Bearer ") or token != GATEWAY_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing gateway token")


# --- Request / Response Models ---

class DirectiveRequest(BaseModel):
    directive_payload: Dict[str, Any]


class ScoringRequest(BaseModel):
    source_identity: str
    destination_identity: str
    requested_liquidity_path: List[str] = Field(..., min_length=2)
    historical_vectors: Dict[str, Any] = Field(default_factory=dict)
    telemetry_data: Dict[str, Any] = Field(default_factory=dict)


# --- Routes ---

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "node_id": os.getenv("NODE_ID", "LOCAL_NODE"),
        "architecture": os.getenv("ARCHITECTURE_MODEL", "INTELLIGENCE_LAYER_ONLY"),
        "custody_allowed": False,
        "tpap_compliance": True,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


@app.post("/v1/directive/validate", dependencies=[Depends(verify_token)])
async def validate_directive(req: DirectiveRequest):
    """
    Validate a raw TPAP directive payload against schema and non-custodial guardrails.
    Returns 200 if valid, 422 with reason if blocked.
    """
    validator = get_validator()
    try:
        validator.validate_directive(req.directive_payload)
        return {
            "valid": True,
            "total_validated": validator.total_validated_directives,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
    except DirectiveValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/v1/directive/execute", dependencies=[Depends(verify_token)])
async def execute_directive(req: DirectiveRequest):
    """
    Validate and execute a full TPAP intelligence pass on a directive payload.
    Returns an optimized routing passport or rejection with reason.
    """
    validator = get_validator()
    orchestrator = get_orchestrator()

    try:
        validator.validate_directive(req.directive_payload)
    except DirectiveValidationError as e:
        raise HTTPException(status_code=422, detail=f"Directive blocked at schema boundary: {e}")

    payload = req.directive_payload
    snapshot = payload["credit_passport_snapshot"]
    routing = payload["routing_instructions"]
    prov = payload["provenance_attestation"]

    context = TransactionContext(
        source_identity=snapshot["identity_hash"],
        destination_identity=routing["destination_gateway"],
        requested_liquidity_path=routing["node_hop_sequence"],
        historical_vectors={
            "repayment_velocity": 1.0,
            "liquidity_utilization": 0.25,
        },
        telemetry_data={
            "source_payload_hash": prov["payload_hash"],
            "is_cryptographically_signed": prov["signature_chain_verified"],
        },
    )

    return orchestrator.execute_intelligence_pass(context)


@app.post("/v1/intelligence/score", dependencies=[Depends(verify_token)])
async def score_context(req: ScoringRequest):
    """
    Run a raw intelligence pass given an explicit transaction context.
    Bypasses directive schema — use for internal agent-to-agent calls.
    """
    orchestrator = get_orchestrator()
    context = TransactionContext(
        source_identity=req.source_identity,
        destination_identity=req.destination_identity,
        requested_liquidity_path=req.requested_liquidity_path,
        historical_vectors=req.historical_vectors,
        telemetry_data=req.telemetry_data,
    )
    return orchestrator.execute_intelligence_pass(context)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
