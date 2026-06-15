-- Sovereign Wallet: adds HD wallet index to merchants and a
-- wallet_index_seq sequence for atomic, collision-free index assignment.

-- Sequence starts at 1 — index 0 is reserved for the oracle/treasury.
create sequence if not exists wallet_index_seq start 1 increment 1;

-- Add wallet_index to merchants (nullable — null means external wallet)
alter table merchants
    add column if not exists wallet_index integer unique;

-- Atomic index claim: increments the sequence and returns the new value.
-- Called by the backend exactly once per merchant to avoid races.
create or replace function claim_next_wallet_index()
returns integer
language sql
security definer
as $$
  select nextval('wallet_index_seq')::integer;
$$;

-- Grant execute to the service role (backend oracle)
grant execute on function claim_next_wallet_index() to service_role;

-- Index for fast lookup by wallet_index
create index if not exists merchants_wallet_index_idx on merchants (wallet_index)
    where wallet_index is not null;
