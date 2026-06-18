-- HITL Review Queue: Michigan Bulletin 2026-03-BT compliance
-- Sweeps above the high-value threshold or W2G-reportable amounts are
-- held here pending human operator sign-off before execution.

CREATE TABLE IF NOT EXISTS hitl_review_queue (
    task_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id         UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    gross_amount        DECIMAL(15,6) NOT NULL,
    source              TEXT NOT NULL DEFAULT 'direct',
    reference_id        TEXT,
    trigger_reason      TEXT NOT NULL,          -- 'W2G_THRESHOLD_TRIGGERED' | 'HIGH_VALUE_SWEEP'
    sweep_breakdown     JSONB NOT NULL,         -- output of calculate_sweep()
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'approved', 'rejected')),
    operator_id         TEXT,                   -- set on resolution
    justification_code  TEXT,
    operator_notes      JSONB DEFAULT '{}'::jsonb,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE hitl_review_queue ENABLE ROW LEVEL SECURITY;

-- Only service role (backend) can write; admins can read
CREATE POLICY "admin_read_hitl_queue" ON hitl_review_queue
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM admin_users WHERE user_id = auth.uid()
        )
    );

CREATE INDEX IF NOT EXISTS idx_hitl_status_created
    ON hitl_review_queue (status, created_at ASC);

-- Add reasoning_trace and operator_id to atomic_sweep_ledger
ALTER TABLE atomic_sweep_ledger
    ADD COLUMN IF NOT EXISTS operator_id      TEXT,
    ADD COLUMN IF NOT EXISTS reasoning_trace  JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS hitl_task_id     UUID REFERENCES hitl_review_queue(task_id);
