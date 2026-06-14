-- Store AI scoring reasoning on each loan so it can be surfaced in
-- WhatsApp notifications and admin views without re-running the scorer.
ALTER TABLE loans
    ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;
