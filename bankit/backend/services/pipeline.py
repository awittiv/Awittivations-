from datetime import datetime, timezone
from services import supabase_service
from services.trust_score import score_loan_request
from services.corridor_service import run_corridor_check
from services.web3_service import release_micro_liquidity, build_trust_score_hash


async def run_approval_pipeline(loan_id: str, merchant_id: str) -> None:
    try:
        merchant = await supabase_service.get_merchant_by_id(merchant_id)
        if not merchant:
            print(f"[Pipeline] Merchant {merchant_id} not found")
            return

        created_at = merchant.get("created_at")
        if created_at:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            merchant_age_days = (datetime.now(timezone.utc) - created_dt).days
        else:
            merchant_age_days = 0

        loan = await supabase_service.get_loan_by_id(loan_id)
        if not loan:
            return

        repayment_history = await supabase_service.get_repayment_history(merchant_id)

        # ── Stage 1: AI Trust Score ─────────────────────────────────────────
        ai_result = await score_loan_request(
            amount_inr=loan["amount_inr"],
            purpose=loan["purpose"],
            business_name=merchant.get("business_name", "Unknown"),
            repayment_history=repayment_history,
            merchant_age_days=merchant_age_days,
        )

        await supabase_service.update_loan(loan_id, {"trust_score": ai_result.score})
        print(f"[Pipeline] Loan {loan_id} — AI score: {ai_result.score} ({ai_result.recommendation})")

        # Hard reject: corridor cannot override
        if ai_result.recommendation == "reject":
            await supabase_service.update_loan(loan_id, {"status": "rejected"})
            print(f"[Pipeline] Loan {loan_id} rejected by AI scorer")
            return

        # ── Stage 2: Corridor Intelligence Pass ─────────────────────────────
        corridor_passport = await run_corridor_check(
            loan_id=loan_id,
            merchant_id=merchant_id,
            amount_inr=loan["amount_inr"],
            repayment_history=repayment_history,
            trust_score=ai_result.score,
        )

        corridor_status = corridor_passport.get("status", "FLAGGED")
        corridor_risk = (
            corridor_passport
            .get("passport_metadata", {})
            .get("credit_metrics", {})
            .get("risk_tier", "MEDIUM")
        )
        corridor_provenance = (
            corridor_passport
            .get("passport_metadata", {})
            .get("provenance_metrics", {})
            .get("provenance_status", "FAILED")
        )

        print(
            f"[Pipeline] Loan {loan_id} — Corridor: {corridor_status} "
            f"(risk={corridor_risk}, provenance={corridor_provenance})"
        )

        # ── Stage 3: Combined Decision Matrix ───────────────────────────────
        #
        # AI=review + corridor APPROVED + LOW risk  → upgrade to approve
        # AI=review + anything else                 → stays pending (human review)
        # AI=approve + corridor APPROVED             → approve → disburse
        # AI=approve + corridor FLAGGED              → downgrade to review
        #
        if ai_result.recommendation == "review":
            if corridor_status == "APPROVED" and corridor_risk == "LOW":
                print(f"[Pipeline] Loan {loan_id} upgraded review→approve by corridor")
                final_decision = "approve"
            else:
                print(f"[Pipeline] Loan {loan_id} flagged for human review (AI=review, corridor={corridor_status})")
                return  # stays pending
        else:
            # AI recommended approve
            if corridor_status == "APPROVED":
                final_decision = "approve"
            else:
                print(
                    f"[Pipeline] Loan {loan_id} downgraded approve→review by corridor "
                    f"(risk={corridor_risk}, provenance={corridor_provenance})"
                )
                return  # downgraded to human review, stays pending

        # ── Stage 4: Approve + Disburse ─────────────────────────────────────
        await supabase_service.update_loan(loan_id, {"status": "approved"})

        wallet_address = merchant.get("wallet_address")
        if not wallet_address:
            print(f"[Pipeline] Loan {loan_id} approved — no wallet address, skipping disbursement")
            return

        trust_score_hash = build_trust_score_hash(loan_id, ai_result.score, ai_result.reasoning)
        tx_hash = await release_micro_liquidity(wallet_address, loan["amount_inr"], trust_score_hash)

        if tx_hash:
            await supabase_service.update_loan(loan_id, {"status": "disbursed", "tx_hash": tx_hash})
            await supabase_service.create_transaction(loan_id, loan["amount_inr"], "disburse", tx_hash)
            print(f"[Pipeline] Loan {loan_id} disbursed — tx {tx_hash}")
        else:
            print(f"[Pipeline] Loan {loan_id} approved but on-chain disbursement failed")

    except Exception as e:
        print(f"[Pipeline] Error processing loan {loan_id}: {e}")
