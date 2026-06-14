-- Credit Passport: tracks the on-chain BankitCreditPassport NFT per merchant.
-- Mirrors on-chain state for fast reads without an RPC call.

create table if not exists credit_passports (
    id              uuid primary key default gen_random_uuid(),
    merchant_id     uuid not null references merchants(id) on delete cascade,
    token_id        bigint not null,
    contract_address text not null,
    mint_tx_hash    text,
    current_score   smallint not null default 0 check (current_score between 0 and 100),
    loans_repaid    integer not null default 0,
    loans_total     integer not null default 0,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (merchant_id),
    unique (token_id, contract_address)
);

-- Fast lookup by merchant
create index if not exists credit_passports_merchant_id_idx on credit_passports (merchant_id);

-- RLS: merchants can only read their own passport
alter table credit_passports enable row level security;

create policy "merchant_read_own_passport"
    on credit_passports for select
    using (
        merchant_id = (
            select id from merchants where user_id = auth.uid()
        )
    );

-- Service role can write freely (backend oracle)
create policy "service_role_all_passport"
    on credit_passports for all
    using (auth.role() = 'service_role');

-- Keep updated_at current
create or replace function update_passport_timestamp()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger passport_updated_at
    before update on credit_passports
    for each row execute procedure update_passport_timestamp();
