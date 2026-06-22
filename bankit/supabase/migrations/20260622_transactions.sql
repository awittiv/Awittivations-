-- Transactions table: records all on-chain disbursements and repayments per loan.
-- Referenced by supabase_service.create_transaction() and get_repayment_history().

CREATE TABLE IF NOT EXISTS transactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_id          UUID NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    amount           DECIMAL(15,2) NOT NULL,
    type             TEXT NOT NULL CHECK (type IN ('disburse', 'repay')),
    polygon_tx_hash  TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Merchants can read transactions for their own loans
CREATE POLICY "merchant_own_transactions" ON transactions
    FOR SELECT TO authenticated
    USING (loan_id IN (
        SELECT id FROM loans
        WHERE merchant_id IN (
            SELECT id FROM merchants WHERE user_id = auth.uid()
        )
    ));

CREATE INDEX IF NOT EXISTS idx_transactions_loan ON transactions (loan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions (type);
