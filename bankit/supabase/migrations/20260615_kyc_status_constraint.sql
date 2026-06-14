-- Fix: kyc_status check constraint was missing 'under_review'.
-- The backend sets this value on document submission; any call was
-- hitting a DB constraint violation and silently failing.

ALTER TABLE merchants
    DROP CONSTRAINT IF EXISTS merchants_kyc_status_check;

ALTER TABLE merchants
    ADD CONSTRAINT merchants_kyc_status_check
    CHECK (kyc_status IN ('pending', 'under_review', 'verified', 'rejected'));
