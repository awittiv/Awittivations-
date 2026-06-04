#!/usr/bin/env python3
"""
Generate a Bankit Trust Scoring API key and store its hash in Supabase.
The raw key is printed ONCE — save it immediately, it cannot be recovered.

Usage:
    python scripts/generate_api_key.py --name "Acme NBFC" --tier growth
"""
import argparse
import hashlib
import os
import secrets
import sys

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

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

    url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")

    client = create_client(url, service_key)

    raw_key = generate_key()
    hashed = hash_key(raw_key)

    result = (
        client.table("api_keys")
        .insert({"name": args.name, "key_hash": hashed, "tier": args.tier})
        .execute()
    )

    record = result.data[0]

    print("\n" + "=" * 60)
    print(f"  Client : {record['name']}")
    print(f"  Tier   : {record['tier']}")
    print(f"  ID     : {record['id']}")
    print(f"\n  API KEY (copy now — shown once):")
    print(f"\n  {raw_key}\n")
    print("=" * 60)
    print("Share this key with your client via a secure channel.")
    print("The raw key is NOT stored — only its SHA-256 hash.\n")


if __name__ == "__main__":
    main()
