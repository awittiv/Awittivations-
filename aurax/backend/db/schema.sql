-- AuraX — Aave v3 Polygon schema (SQLite-compatible)
-- Column names match the Claude NL-to-SQL prompt exactly

CREATE TABLE IF NOT EXISTS reserves (
    reserve_id            TEXT PRIMARY KEY,
    symbol                TEXT NOT NULL,
    name                  TEXT,
    decimals              INTEGER,
    liquidity_rate        REAL,
    variable_borrow_rate  REAL,
    stable_borrow_rate    REAL,
    utilization_rate      REAL,
    total_atoken_supply   REAL,
    total_variable_debt   REAL,
    total_stable_debt     REAL,
    price_usd             REAL,
    tvl_usd               REAL,
    is_active             INTEGER DEFAULT 1,
    is_frozen             INTEGER DEFAULT 0,
    updated_at            TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reserve_history (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    reserve_id            TEXT NOT NULL,
    symbol                TEXT NOT NULL,
    liquidity_rate        REAL,
    variable_borrow_rate  REAL,
    utilization_rate      REAL,
    tvl_usd               REAL,
    snapshot_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rh_reserve_time ON reserve_history (reserve_id, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS supply_events (
    tx_hash        TEXT PRIMARY KEY,
    block_number   INTEGER,
    block_time     TEXT,
    user_address   TEXT,
    reserve_id     TEXT,
    symbol         TEXT,
    amount         REAL,
    amount_usd     REAL
);

CREATE TABLE IF NOT EXISTS withdraw_events (
    tx_hash        TEXT PRIMARY KEY,
    block_number   INTEGER,
    block_time     TEXT,
    user_address   TEXT,
    reserve_id     TEXT,
    symbol         TEXT,
    amount         REAL,
    amount_usd     REAL
);

CREATE TABLE IF NOT EXISTS borrow_events (
    tx_hash           TEXT PRIMARY KEY,
    block_number      INTEGER,
    block_time        TEXT,
    user_address      TEXT,
    reserve_id        TEXT,
    symbol            TEXT,
    amount_usd        REAL,
    borrow_rate_mode  INTEGER,
    borrow_rate       REAL
);

CREATE TABLE IF NOT EXISTS liquidation_events (
    tx_hash                TEXT PRIMARY KEY,
    block_number           INTEGER,
    block_time             TEXT,
    collateral_symbol      TEXT,
    debt_symbol            TEXT,
    user_address           TEXT,
    liquidator_address     TEXT,
    debt_covered_usd       REAL,
    collateral_seized_usd  REAL
);
