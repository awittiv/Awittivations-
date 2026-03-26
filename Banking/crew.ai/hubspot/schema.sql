-- 1. Agentic Identity Store (Visa Agentic Ready Spec)
-- Assigns a unique 'Agent ID' to your AI logic for the Visa network.
CREATE TABLE IF NOT EXISTS agentic_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(50) DEFAULT 'Bankit-Alpha-01',
    visa_agent_token TEXT,       -- From the new Visa Agentic SDK
    logic_hash TEXT,             -- SHA-256 of your current Python logic code
    verified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Base table for ais_program_audit (assuming it didn't exist before, creating a minimal version)
CREATE TABLE IF NOT EXISTS ais_program_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agentic_identities(id),
    action_taken TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Enhanced AIS Audit (Michigan 2026-03-BT "Safe Harbor" Edition)
-- Adds mandatory 'Fairness' and 'Validation' fields to protect the LLC.
ALTER TABLE ais_program_audit 
ADD COLUMN IF NOT EXISTS fairness_score DECIMAL(3,2), -- 0.00 to 1.00 (Bias Detection)
ADD COLUMN IF NOT EXISTS validation_hash TEXT,        -- Proves the code wasn't tampered with
ADD COLUMN IF NOT EXISTS model_version VARCHAR(20) DEFAULT 'Bankit-v9.0';
