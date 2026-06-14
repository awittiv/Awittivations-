-- Add error tracking to loans so pipeline failures are visible in the DB.
-- When the AI scorer, corridor check, or on-chain disbursal fails,
-- the reason is stored here instead of only in server logs.

ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS error_reason TEXT,
    ADD COLUMN IF NOT EXISTS error_at    TIMESTAMP WITH TIME ZONE;
