-- Bankit × HubSpot integration schema
-- Tracks sync state between bankit entities and HubSpot CRM objects

CREATE TABLE IF NOT EXISTS hubspot_contact_sync (
    id              SERIAL PRIMARY KEY,
    merchant_id     TEXT NOT NULL UNIQUE,
    hubspot_contact_id TEXT NOT NULL,
    business_name   TEXT,
    phone           TEXT,
    trust_score     INTEGER,
    synced_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hubspot_deal_sync (
    id              SERIAL PRIMARY KEY,
    loan_id         TEXT NOT NULL UNIQUE,
    merchant_id     TEXT NOT NULL REFERENCES hubspot_contact_sync(merchant_id),
    hubspot_deal_id TEXT NOT NULL,
    amount_inr      NUMERIC(15, 2),
    purpose         TEXT,
    status          TEXT CHECK (status IN ('pending', 'approved', 'disbursed', 'repaid', 'rejected')),
    synced_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hubspot_sync_log (
    id          SERIAL PRIMARY KEY,
    run_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    contacts_synced INTEGER DEFAULT 0,
    deals_created   INTEGER DEFAULT 0,
    errors          TEXT,
    status      TEXT CHECK (status IN ('success', 'partial', 'failed'))
);

-- Agentic Identity Store (Visa Agentic Ready Spec)
CREATE TABLE IF NOT EXISTS agentic_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(50) DEFAULT 'Bankit-Alpha-01',
    visa_agent_token TEXT,
    logic_hash TEXT,
    verified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ais_program_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agentic_identities(id),
    action_taken TEXT,
    fairness_score DECIMAL(3,2),
    validation_hash TEXT,
    model_version VARCHAR(20) DEFAULT 'Bankit-v9.0',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Keep updated_at current automatically
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_contact_sync_updated
    BEFORE UPDATE ON hubspot_contact_sync
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_deal_sync_updated
    BEFORE UPDATE ON hubspot_deal_sync
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
