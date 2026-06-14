"""
Service: sweep_engine.py
Implements the Atomic Sweep logic: real-time tax withholding on payment ingestion.

On every dollar of revenue received by a merchant, the sweep engine instantly
calculates and records Michigan state tax (4.25%), Muskegon city tax (1.0%),
and an estimated federal withholding (22%), crediting only the net amount.

Compliant with Michigan Bulletin 2026-03-BT and IRS 1099-NEC/W-2G thresholds.
"""

from services import supabase_service
from services.web3_service import release_micro_liquidity, build_trust_score_hash
import hashlib

MI_STATE_RATE = 0.0425       # Michigan flat income tax
MUSKEGON_CITY_RATE = 0.0100  # Muskegon city income tax
FEDERAL_ESTIMATE_RATE = 0.22  # Federal income tax estimate for gig/1099 workers

# IRS W-2G single-payment reporting threshold
W2G_REPORTING_THRESHOLD = 600.00


def calculate_sweep(gross_amount: float) -> dict:
    """
    Calculate the Atomic Sweep breakdown for a given gross payment.
    Returns a dict with all withholding amounts and the net credit.
    """
    mi_state = round(gross_amount * MI_STATE_RATE, 6)
    muskegon_city = round(gross_amount * MUSKEGON_CITY_RATE, 6)
    federal = round(gross_amount * FEDERAL_ESTIMATE_RATE, 6)
    total_withheld = round(mi_state + muskegon_city + federal, 6)
    net = round(gross_amount - total_withheld, 6)

    return {
        "gross_amount": gross_amount,
        "mi_state_withholding": mi_state,
        "muskegon_city_withholding": muskegon_city,
        "federal_withholding": federal,
        "total_withheld": total_withheld,
        "net_amount": net,
        "effective_rate": round(total_withheld / gross_amount, 4) if gross_amount else 0,
        "w2g_reportable": gross_amount >= W2G_REPORTING_THRESHOLD,
    }


async def execute_atomic_sweep(
    merchant_id: str,
    merchant_wallet: str | None,
    gross_amount: float,
    source: str = "direct",
    reference_id: str | None = None,
) -> dict:
    """
    Execute a full Atomic Sweep:
    1. Calculate tax withholdings
    2. Record the sweep in the audit ledger
    3. Mint BKD net amount to the merchant's wallet (if wallet configured)
    4. Return the full sweep result

    This is the core of the 'Zero-Click' compliance model.
    """
    sweep = calculate_sweep(gross_amount)

    tx_hash = None
    if merchant_wallet and sweep["net_amount"] > 0:
        sweep_hash = hashlib.sha256(
            f"{merchant_id}:{gross_amount}:{source}:{reference_id}".encode()
        ).hexdigest()
        score_hash = build_trust_score_hash(
            reference_id or sweep_hash, 100, "atomic-sweep"
        )
        tx_hash = await release_micro_liquidity(merchant_wallet, sweep["net_amount"], score_hash)

    client = supabase_service.get_client()
    result = client.table("atomic_sweep_ledger").insert({
        "merchant_id": merchant_id,
        "gross_amount": sweep["gross_amount"],
        "mi_state_withholding": sweep["mi_state_withholding"],
        "muskegon_city_withholding": sweep["muskegon_city_withholding"],
        "federal_withholding": sweep["federal_withholding"],
        "net_amount": sweep["net_amount"],
        "source": source,
        "reference_id": reference_id,
        "sweep_status": "completed",
        "tx_hash": tx_hash,
    }).execute()

    return {**sweep, "sweep_id": result.data[0]["id"], "tx_hash": tx_hash}


async def get_sweep_summary(merchant_id: str) -> dict:
    """
    Return aggregate sweep stats for a merchant (ytd gross, withheld, net).
    Used by the merchant dashboard and for W-2G threshold monitoring.
    """
    client = supabase_service.get_client()
    rows = client.table("atomic_sweep_ledger").select(
        "gross_amount, mi_state_withholding, muskegon_city_withholding, federal_withholding, net_amount"
    ).eq("merchant_id", merchant_id).eq("sweep_status", "completed").execute()

    if not rows.data:
        return {
            "ytd_gross": 0, "ytd_withheld": 0, "ytd_net": 0,
            "ytd_mi_state": 0, "ytd_muskegon": 0, "ytd_federal": 0,
            "w2g_threshold_reached": False, "sweep_count": 0,
        }

    ytd_gross = sum(float(r["gross_amount"]) for r in rows.data)
    ytd_mi = sum(float(r["mi_state_withholding"]) for r in rows.data)
    ytd_muskegon = sum(float(r["muskegon_city_withholding"]) for r in rows.data)
    ytd_federal = sum(float(r["federal_withholding"]) for r in rows.data)
    ytd_net = sum(float(r["net_amount"]) for r in rows.data)

    return {
        "ytd_gross": round(ytd_gross, 2),
        "ytd_withheld": round(ytd_mi + ytd_muskegon + ytd_federal, 2),
        "ytd_net": round(ytd_net, 2),
        "ytd_mi_state": round(ytd_mi, 2),
        "ytd_muskegon": round(ytd_muskegon, 2),
        "ytd_federal": round(ytd_federal, 2),
        "w2g_threshold_reached": ytd_gross >= W2G_REPORTING_THRESHOLD,
        "sweep_count": len(rows.data),
    }
