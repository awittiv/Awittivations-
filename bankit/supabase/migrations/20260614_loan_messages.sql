-- WhatsApp conversation log: inbound/outbound messages tied to a loan
-- Created separately from the initial schema because the table was used before being migrated.

CREATE TABLE IF NOT EXISTS loan_messages (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_id      UUID NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    direction    TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    content      TEXT NOT NULL,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_loan_messages_loan_id
    ON loan_messages (loan_id, created_at DESC);

ALTER TABLE loan_messages ENABLE ROW LEVEL SECURITY;

-- Merchants can only read messages for their own loans
CREATE POLICY "merchant_read_own_messages" ON loan_messages
    FOR SELECT
    USING (
        loan_id IN (
            SELECT id FROM loans
            WHERE merchant_id IN (
                SELECT id FROM merchants WHERE user_id = auth.uid()
            )
        )
    );

-- Merchants cannot write directly — messages are written by the backend via service role
-- No INSERT/UPDATE/DELETE policy for authenticated users.
