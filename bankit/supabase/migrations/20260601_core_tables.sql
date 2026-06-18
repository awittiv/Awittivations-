-- Core tables: merchants and loans
-- Foundation required by all other migrations.

CREATE TABLE IF NOT EXISTS merchants (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    business_name    TEXT NOT NULL,
    phone            TEXT UNIQUE,
    wallet_address   TEXT,
    kyc_status       TEXT NOT NULL DEFAULT 'pending'
                         CHECK (kyc_status IN ('pending', 'submitted', 'approved', 'rejected')),
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE merchants ENABLE ROW LEVEL SECURITY;

CREATE POLICY "merchant_own_row" ON merchants
    FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS idx_merchants_user   ON merchants (user_id);
CREATE INDEX IF NOT EXISTS idx_merchants_phone  ON merchants (phone);

-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS loans (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id  UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    amount_inr   DECIMAL(15,2) NOT NULL,
    purpose      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'disbursed', 'repaid', 'rejected')),
    trust_score  INTEGER,
    tx_hash      TEXT,
    error_reason TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE loans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "merchant_own_loans" ON loans
    FOR ALL TO authenticated
    USING (merchant_id IN (
        SELECT id FROM merchants WHERE user_id = auth.uid()
    ));

CREATE INDEX IF NOT EXISTS idx_loans_merchant ON loans (merchant_id, created_at DESC);
