from datetime import datetime, timezone
from services import supabase_service
from services.trust_score import score_loan_request
from services.corridor_service import run_corridor_check
from services.sweep_engine import execute_atomic_sweep
from services.web3_service import release_micro_liquidity, build_trust_score_hash, mint_credit_passport, update_credit_passport, get_passport_token_id


async def run_approval_pipeline(loan_id: str, merchant_id: str) -> None:
    try:
        merchant = await supabase_service.get_merchant_by_id(merchant_id)
        if not merchant:
            print(f"[Pipeline] Merchant {merchant_id} not found")
            return

        # ── KYC Gate ────────────────────────────────────────────────────────────
        kyc_status = merchant.get("kyc_status", "pending")
        if kyc_status != "verified":
            if kyc_status == "pending":
                await supabase_service.update_loan(loan_id, {"status": "rejected"})
                print(f"[Pipeline] Loan {loan_id} rejected — KYC documents not submitted")
            elif kyc_status == "rejected":
                await supabase_service.update_loan(loan_id, {"status": "rejected"})
                print(f"[Pipeline] Loan {loan_id} rejected — KYC rejected by admin")
            else:
                # under_review: docs submitted but admin hasn't verified yet
                print(f"[Pipeline] Loan {loan_id} held for human review — KYC status: {kyc_status}")
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

        await supabase_service.update_loan(loan_id, {"trust_score": ai_result.score, "ai_reasoning": ai_result.reasoning})
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

        # Atomic claim — guards against duplicate pipeline runs (e.g. Twilio webhook retries)
        claimed = await supabase_service.claim_disbursement(loan_id)
        if not claimed:
            print(f"[Pipeline] Loan {loan_id} disbursement already claimed — skipping")
            return

        trust_score_hash = build_trust_score_hash(loan_id, ai_result.score, ai_result.reasoning)
        tx_hash = await release_micro_liquidity(wallet_address, loan["amount_inr"], trust_score_hash)

        if tx_hash:
            await supabase_service.update_loan(loan_id, {"status": "disbursed", "tx_hash": tx_hash})
            await supabase_service.create_transaction(loan_id, loan["amount_inr"], "disburse", tx_hash)
            print(f"[Pipeline] Loan {loan_id} disbursed — tx {tx_hash}")

            # ── Atomic Sweep: real-time tax withholding on disbursement ─────
            try:
                await execute_atomic_sweep(
                    merchant_id=merchant_id,
                    merchant_wallet=wallet_address,
                    gross_amount=float(loan["amount_inr"]),
                    source="loan_disbursal",
                    reference_id=loan_id,
                )
                print(f"[Pipeline] Loan {loan_id} — Atomic Sweep recorded")
            except Exception as sweep_err:
                print(f"[Pipeline] Loan {loan_id} — Atomic Sweep failed (non-blocking): {sweep_err}")

            # ── Credit Passport: mint on first approval, update thereafter ──
            try:
                existing_token = get_passport_token_id(merchant_id)
                if existing_token is None:
                    passport_tx = await mint_credit_passport(
                        wallet_address, merchant_id, ai_result.score
                    )
                    print(f"[Pipeline] Loan {loan_id} — Credit Passport minted (tx {passport_tx})")
                else:
                    passport_tx = await update_credit_passport(
                        merchant_id, ai_result.score, loan_repaid=False
                    )
                    print(f"[Pipeline] Loan {loan_id} — Credit Passport updated (tx {passport_tx})")
            except Exception as passport_err:
                print(f"[Pipeline] Loan {loan_id} — Passport update failed (non-blocking): {passport_err}")
        else:
            reason = "On-chain disbursement returned no tx_hash — RPC or contract error"
            # Revert claim so the loan stays approved and admin can manually disburse
            await supabase_service.update_loan(loan_id, {"tx_hash": None, "error_reason": reason})
            print(f"[Pipeline] Loan {loan_id} approved but on-chain disbursement failed")

    except Exception as e:
        print(f"[Pipeline] Error processing loan {loan_id}: {e}")
        try:
            await supabase_service.update_loan(loan_id, {"error_reason": str(e)[:500]})
        except Exception:
            pass
