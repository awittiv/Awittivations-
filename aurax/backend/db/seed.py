"""
Seed local SQLite DB with realistic Aave v3 Polygon mock data.
Run: python -m backend.db.seed
"""
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("SQLITE_PATH", "aurax.db")
RAY = 1e25

RESERVES = [
    {"reserve_id": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174", "symbol": "USDC",  "name": "USD Coin",       "decimals": 6,  "deposit_apy": 5.20, "variable_borrow_apy": 7.80, "stable_borrow_apy": 9.10, "utilization_rate": 0.76, "tvl_usd": 182_000_000, "price_usd": 1.00},
    {"reserve_id": "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619", "symbol": "WETH",  "name": "Wrapped Ether",  "decimals": 18, "deposit_apy": 2.85, "variable_borrow_apy": 4.20, "stable_borrow_apy": 5.50, "utilization_rate": 0.63, "tvl_usd": 124_000_000, "price_usd": 3520.00},
    {"reserve_id": "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270", "symbol": "WMATIC","name": "Wrapped Matic",  "decimals": 18, "deposit_apy": 4.10, "variable_borrow_apy": 6.30, "stable_borrow_apy": 7.80, "utilization_rate": 0.71, "tvl_usd": 46_000_000,  "price_usd": 0.87},
    {"reserve_id": "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6", "symbol": "WBTC",  "name": "Wrapped Bitcoin", "decimals": 8,  "deposit_apy": 1.55, "variable_borrow_apy": 2.90, "stable_borrow_apy": 4.10, "utilization_rate": 0.54, "tvl_usd": 62_000_000,  "price_usd": 67200.00},
    {"reserve_id": "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", "symbol": "DAI",   "name": "Dai Stablecoin", "decimals": 18, "deposit_apy": 4.80, "variable_borrow_apy": 7.10, "stable_borrow_apy": 8.60, "utilization_rate": 0.73, "tvl_usd": 98_000_000,  "price_usd": 1.00},
    {"reserve_id": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "symbol": "USDT",  "name": "Tether USD",     "decimals": 6,  "deposit_apy": 5.00, "variable_borrow_apy": 7.40, "stable_borrow_apy": 8.90, "utilization_rate": 0.74, "tvl_usd": 88_000_000,  "price_usd": 1.00},
    {"reserve_id": "0xd6df932a45c0f255f85145f286ea0b292b21c90b", "symbol": "AAVE",  "name": "Aave Token",     "decimals": 18, "deposit_apy": 0.32, "variable_borrow_apy": 0.90, "stable_borrow_apy": 2.10, "utilization_rate": 0.19, "tvl_usd": 29_000_000,  "price_usd": 285.00},
    {"reserve_id": "0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39", "symbol": "LINK",  "name": "ChainLink Token", "decimals": 18, "deposit_apy": 1.20, "variable_borrow_apy": 2.40, "stable_borrow_apy": 3.80, "utilization_rate": 0.41, "tvl_usd": 19_000_000,  "price_usd": 18.50},
]

WALLETS = [f"0x{uuid.uuid4().hex[:40]}" for _ in range(80)]


def ray(pct: float) -> float:
    return pct * RAY


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def seed():
    schema_sql = Path("backend/db/schema.sql").read_text()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    async with aiosqlite.connect(DB_PATH) as db:
        # ── schema ────────────────────────────────────────────────
        for stmt in schema_sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()

        # ── clear existing data ───────────────────────────────────
        for tbl in ("reserves", "reserve_history", "supply_events", "withdraw_events", "borrow_events", "liquidation_events"):
            await db.execute(f"DELETE FROM {tbl}")
        await db.commit()

        # ── reserves ──────────────────────────────────────────────
        for r in RESERVES:
            supply = r["tvl_usd"] / r["price_usd"]
            debt = supply * r["utilization_rate"]
            await db.execute(
                "INSERT INTO reserves VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,?)",
                (r["reserve_id"], r["symbol"], r["name"], r["decimals"],
                 ray(r["deposit_apy"]), ray(r["variable_borrow_apy"]), ray(r["stable_borrow_apy"]),
                 r["utilization_rate"], supply, debt * 0.9, debt * 0.1,
                 r["price_usd"], r["tvl_usd"], ts(now)),
            )
        await db.commit()
        print(f"  Inserted {len(RESERVES)} reserves")

        # ── reserve_history — 30 days hourly ──────────────────────
        history_rows = []
        for r in RESERVES:
            for h in range(30 * 24):
                snap = now - timedelta(hours=h)
                drift = random.uniform(-0.3, 0.3)
                history_rows.append((
                    r["reserve_id"], r["symbol"],
                    ray(max(0.01, r["deposit_apy"] + drift)),
                    ray(max(0.01, r["variable_borrow_apy"] + drift * 1.5)),
                    max(0.05, min(0.99, r["utilization_rate"] + random.uniform(-0.04, 0.04))),
                    r["tvl_usd"] * (1 + random.uniform(-0.02, 0.02)),
                    ts(snap),
                ))
        await db.executemany(
            "INSERT INTO reserve_history (reserve_id,symbol,liquidity_rate,variable_borrow_rate,utilization_rate,tvl_usd,snapshot_at) VALUES (?,?,?,?,?,?,?)",
            history_rows,
        )
        await db.commit()
        print(f"  Inserted {len(history_rows)} reserve_history rows")

        # ── supply_events ─────────────────────────────────────────
        supply_rows = [
            (f"0x{uuid.uuid4().hex}", random.randint(50_000_000, 55_000_000),
             ts(now - timedelta(hours=random.randint(0, 720))),
             random.choice(WALLETS), (r := random.choice(RESERVES))["reserve_id"], r["symbol"],
             (amt := random.uniform(500, 250_000)) / r["price_usd"], amt)
            for _ in range(600)
        ]
        await db.executemany(
            "INSERT INTO supply_events VALUES (?,?,?,?,?,?,?,?)", supply_rows
        )
        await db.commit()
        print(f"  Inserted {len(supply_rows)} supply_events")

        # ── borrow_events ─────────────────────────────────────────
        borrow_rows = [
            (f"0x{uuid.uuid4().hex}", random.randint(50_000_000, 55_000_000),
             ts(now - timedelta(hours=random.randint(0, 720))),
             random.choice(WALLETS), (r := random.choice(RESERVES))["reserve_id"], r["symbol"],
             random.uniform(200, 100_000), random.choice([1, 2]),
             ray(r["variable_borrow_apy"] * random.uniform(0.95, 1.05)))
            for _ in range(300)
        ]
        await db.executemany(
            "INSERT INTO borrow_events VALUES (?,?,?,?,?,?,?,?,?)", borrow_rows
        )
        await db.commit()
        print(f"  Inserted {len(borrow_rows)} borrow_events")

        # ── liquidation_events ────────────────────────────────────
        col_assets = [r for r in RESERVES if r["symbol"] in ("WETH", "WBTC", "WMATIC")]
        dbt_assets = [r for r in RESERVES if r["symbol"] in ("USDC", "DAI", "USDT")]
        liq_rows = [
            (f"0x{uuid.uuid4().hex}", random.randint(50_000_000, 55_000_000),
             ts(now - timedelta(hours=random.randint(0, 720))),
             (col := random.choice(col_assets))["symbol"],
             (dbt := random.choice(dbt_assets))["symbol"],
             random.choice(WALLETS), random.choice(WALLETS),
             (d := random.uniform(1_000, 80_000)), d * random.uniform(1.04, 1.12))
            for _ in range(40)
        ]
        await db.executemany(
            "INSERT INTO liquidation_events VALUES (?,?,?,?,?,?,?,?,?)", liq_rows
        )
        await db.commit()
        print(f"  Inserted {len(liq_rows)} liquidation_events")

    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
