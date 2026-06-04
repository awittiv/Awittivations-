-- API key table for the Bankit Trust Scoring API (B2B / NBFC clients)

CREATE TABLE IF NOT EXISTS api_keys (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL,                          -- e.g. "Acme NBFC"
    key_hash             TEXT NOT NULL UNIQUE,                   -- SHA-256 of raw key
    tier                 TEXT NOT NULL DEFAULT 'starter'
                             CHECK (tier IN ('starter', 'growth', 'enterprise')),
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    requests_this_month  INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at         TIMESTAMP WITH TIME ZONE
);

-- Atomic increment used after each successful /v1/score call
CREATE OR REPLACE FUNCTION increment_api_key_usage(key_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE api_keys
    SET requests_this_month = requests_this_month + 1,
        last_used_at = NOW()
    WHERE id = key_id;
END;
$$ LANGUAGE plpgsql;

-- Reset usage counters on the 1st of each month (run via pg_cron or Supabase scheduled function)
CREATE OR REPLACE FUNCTION reset_monthly_usage()
RETURNS VOID AS $$
BEGIN
    UPDATE api_keys SET requests_this_month = 0;
END;
$$ LANGUAGE plpgsql;
