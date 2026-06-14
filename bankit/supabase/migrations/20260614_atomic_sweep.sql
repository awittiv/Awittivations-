-- Atomic Sweep ledger: records real-time tax withholding on each payment ingestion.
-- Every dollar earned by a merchant/worker flows through this table before net disbursement.
-- Michigan Bulletin 2026-03-BT compliance: per-transaction audit trail required.

CREATE TABLE IF NOT EXISTS atomic_sweep_ledger (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id                 UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    gross_amount                DECIMAL(15,6) NOT NULL,
    mi_state_withholding        DECIMAL(15,6) NOT NULL,  -- 4.25% Michigan state
    muskegon_city_withholding   DECIMAL(15,6) NOT NULL,  -- 1.00% Muskegon city
    federal_withholding         DECIMAL(15,6) NOT NULL,  -- 22% federal estimate (gig/1099)
    net_amount                  DECIMAL(15,6) NOT NULL,
    source                      TEXT NOT NULL DEFAULT 'direct',  -- stripe | w2g | direct | readybucks
    reference_id                TEXT,                            -- upstream payment ID
    sweep_status                TEXT NOT NULL DEFAULT 'completed'
                                    CHECK (sweep_status IN ('completed', 'pending', 'failed')),
    tx_hash                     TEXT,                            -- BKD mint tx for net amount
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE atomic_sweep_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY "merchant_own_sweeps" ON atomic_sweep_ledger
    FOR SELECT TO authenticated
    USING (merchant_id IN (
        SELECT id FROM merchants WHERE user_id = auth.uid()
    ));

-- Index for per-merchant time-ordered queries (dashboard, reporting)
CREATE INDEX IF NOT EXISTS idx_sweep_merchant_created
    ON atomic_sweep_ledger (merchant_id, created_at DESC);
