-- Non-custodial rails: SBA + NSFI grant tracking for all Awittivations projects
create table if not exists rails_grants (
    id                  uuid primary key default gen_random_uuid(),
    project_name        text not null check (project_name in ('bankit','brf','launchlayer','awittivations_main')),
    sba_program         text not null check (sba_program in ('sba_7a','sba_sblc','sba_made_in_america','sba_eidl','sba_microloan','nsfi')),
    amount_usd_cents    bigint not null check (amount_usd_cents > 0),
    description         text not null,
    nsfi_pillars        text[] not null default '{}',
    application_ref     text,
    beneficiary_wallet  text not null,
    status              text not null default 'pending'
                            check (status in ('pending','attested','committed','claimed','cancelled','rejected')),
    compliance_hash     text,
    grant_id_onchain    text,
    attestation_tx      text,
    commitment_tx       text,
    claim_tx            text,
    rejection_reason    text,
    -- Awittivations LLC federal entity identifiers (stamped at creation)
    entity_uei          text default 'L6H1T8L7ZJC6',
    entity_duns         text default '14-4151378',
    entity_ein          text default '900158942',
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists rails_grants_project_idx on rails_grants (project_name);
create index if not exists rails_grants_status_idx  on rails_grants (status);
create index if not exists rails_grants_wallet_idx  on rails_grants (beneficiary_wallet);

-- RLS: service role only (rails backend uses service role key)
alter table rails_grants enable row level security;
create policy "service role full access" on rails_grants
    using (auth.role() = 'service_role');
