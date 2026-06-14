from datetime import datetime, timezone
from services import supabase_service
from services.trust_score import score_loan_request
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

        result = await score_loan_request(
            amount_inr=loan["amount_inr"],
            purpose=loan["purpose"],
            business_name=merchant.get("business_name", "Unknown"),
            repayment_history=repayment_history,
            merchant_age_days=merchant_age_days,
        )

        await supabase_service.update_loan(loan_id, {"trust_score": result.score})
        print(f"[Pipeline] Loan {loan_id} scored {result.score} → {result.recommendation}")

        if result.recommendation == "reject":
            await supabase_service.update_loan(loan_id, {"status": "rejected"})
            return

        if result.recommendation == "review":
            # Score saved, stays pending for human review
            return

        # Approve
        await supabase_service.update_loan(loan_id, {"status": "approved"})

        wallet_address = merchant.get("wallet_address")
        if not wallet_address:
            print(f"[Pipeline] Loan {loan_id} approved — no wallet address, skipping disbursement")
            return

        trust_score_hash = build_trust_score_hash(loan_id, result.score, result.reasoning)
        tx_hash = await release_micro_liquidity(wallet_address, loan["amount_inr"], trust_score_hash)

        if tx_hash:
            await supabase_service.update_loan(loan_id, {"status": "disbursed", "tx_hash": tx_hash})
            await supabase_service.create_transaction(loan_id, loan["amount_inr"], "disburse", tx_hash)
            print(f"[Pipeline] Loan {loan_id} disbursed — tx {tx_hash}")
        else:
            # Stays approved; disbursement can be retried manually
            print(f"[Pipeline] Loan {loan_id} approved but on-chain disbursement failed")

    except Exception as e:
        print(f"[Pipeline] Error processing loan {loan_id}: {e}")
