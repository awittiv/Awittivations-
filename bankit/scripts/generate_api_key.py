#!/usr/bin/env python3
"""
Generate a Bankit Trust Scoring API key and store its hash in the database.
The raw key is printed ONCE — save it immediately, it cannot be recovered.

Usage:
    python scripts/generate_api_key.py --name "Acme NBFC" --tier growth
"""
import argparse
import hashlib
import os
import secrets

import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../backend/.env"))

TIERS = ("starter", "growth", "enterprise")


def generate_key() -> str:
    return "sk_live_" + secrets.token_urlsafe(32)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Generate a Bankit API key")
    parser.add_argument("--name", required=True, help="Client name, e.g. 'Acme NBFC'")
    parser.add_argument("--tier", default="starter", choices=TIERS, help="Pricing tier")
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", 5432),
        dbname=os.environ.get("DB_NAME", "postgres"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ["DB_PASSWORD"],
        sslmode="require",
    )

    raw_key = generate_key()
    hashed = hash_key(raw_key)

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_keys (name, key_hash, tier)
                VALUES (%s, %s, %s)
                RETURNING id, name, tier, created_at
                """,
                (args.name, hashed, args.tier),
            )
            row = cur.fetchone()

    conn.close()

    print("\n" + "=" * 60)
    print(f"  Client : {row[1]}")
    print(f"  Tier   : {row[2]}")
    print(f"  ID     : {row[0]}")
    print("\n  API KEY (copy now — shown once):\n")
    print(f"  {raw_key}\n")
    print("=" * 60)
    print("Share via secure channel. Raw key NOT stored.\n")


if __name__ == "__main__":
    main()
