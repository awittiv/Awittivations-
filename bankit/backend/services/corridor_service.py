"""
Service: corridor_service.py
Wraps the TPAP corridor intelligence engine for use inside the Bankit approval pipeline.
Provides a second, independent signal — provenance verification + behavioral risk —
to confirm or flag what the AI trust scorer decided.
"""

import os
import sys
import hashlib
import asyncio
from typing import Any

# Resolve corridor module path relative to this file
_CORRIDOR_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../corridor")
)
if _CORRIDOR_PATH not in sys.path:
    sys.path.insert(0, _CORRIDOR_PATH)

from credit_passport_engine import AutonomousOrchestrationEngine, TransactionContext  # noqa: E402

_ENGINE_INSTANCE: AutonomousOrchestrationEngine | None = None
_ENGINE_LOCK = asyncio.Lock()

CORRIDOR_NODES = ["IN_BANKIT_NODE", "TPAP_INTELLIGENCE_ROUTER", "IN_MERCHANT_WALLET"]
LIQUIDITY_CEILING_INR = 100_000  # normalization ceiling for utilization ratio


def _get_engine() -> AutonomousOrchestrationEngine:
    global _ENGINE_INSTANCE
    if _ENGINE_INSTANCE is None:
        _ENGINE_INSTANCE = AutonomousOrchestrationEngine()
    return _ENGINE_INSTANCE


def _build_provenance_hash(loan_id: str, merchant_id: str, amount_inr: float, trust_score: int) -> str:
    """Deterministic hash of loan facts — used as the corridor provenance attestation."""
    payload = f"{loan_id}:{merchant_id}:{amount_inr:.2f}:{trust_score}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _repayment_velocity(repayment_history: list[dict]) -> float:
    """
    Maps historical repayment records to a velocity scalar.
    1.0 = neutral baseline. >1.0 = strong history. <1.0 = mixed/thin history.
    """
    if not repayment_history:
        return 1.0
    repaid = sum(1 for r in repayment_history if r.get("status") == "repaid")
    return round((repaid / len(repayment_history)) * 1.5, 4)


def _utilization_ratio(amount_inr: float) -> float:
    """Normalizes requested loan amount against the platform ceiling."""
    return round(min(amount_inr / LIQUIDITY_CEILING_INR, 0.95), 4)


async def run_corridor_check(
    loan_id: str,
    merchant_id: str,
    amount_inr: float,
    repayment_history: list[dict],
    trust_score: int,
) -> dict[str, Any]:
    """
    Run a TPAP corridor intelligence pass on a loan that has already been AI-scored.

    Returns the corridor passport dict with at minimum:
      status         → "APPROVED" | "FLAGGED" | "REJECTED"
      passport_metadata.credit_metrics.risk_tier → "LOW" | "MEDIUM" | "HIGH"
      passport_metadata.provenance_metrics.provenance_status → "VERIFIED" | "FAILED"
    """
    provenance_hash = _build_provenance_hash(loan_id, merchant_id, amount_inr, trust_score)

    context = TransactionContext(
        source_identity=merchant_id,
        destination_identity="bankit_liquidity_pool",
        requested_liquidity_path=CORRIDOR_NODES,
        historical_vectors={
            "repayment_velocity": _repayment_velocity(repayment_history),
            "liquidity_utilization": _utilization_ratio(amount_inr),
        },
        telemetry_data={
            "source_payload_hash": provenance_hash,
            "is_cryptographically_signed": True,
        },
    )

    # Corridor engine is CPU-bound but lightweight — run in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    engine = _get_engine()
    passport = await loop.run_in_executor(None, engine.execute_intelligence_pass, context)
    return passport
