"""
Sovereign Wallet Service — BIP-44 HD wallet management for Bankit.

All wallets (oracle + every merchant) derive from a single master seed phrase
stored in WALLET_MASTER_SEED. Private keys are never stored — always re-derived
on demand. Each merchant gets a unique Polygon address auto-assigned at signup.

Derivation paths (BIP-44, Polygon = coin type 60):
  Oracle   / treasury : m/44'/60'/0'/0/0
  Merchants           : m/44'/60'/0'/0/{wallet_index}   (index ≥ 1)

Operators must back up WALLET_MASTER_SEED — losing it loses access to all
sovereign merchant wallets. Store it in a secrets manager (not just .env).
"""

import os
import logging
from eth_account import Account

Account.enable_unaudited_hdwallet_features()

logger = logging.getLogger(__name__)

_DERIVATION_BASE = "m/44'/60'/0'/0"
ORACLE_INDEX = 0  # index 0 is always the oracle/treasury


def _get_master_seed() -> str:
    seed = os.getenv("WALLET_MASTER_SEED", "")
    if not seed:
        raise RuntimeError(
            "WALLET_MASTER_SEED is not set. "
            "Generate one with: python3 -c \"from eth_account import Account; "
            "Account.enable_unaudited_hdwallet_features(); "
            "_, m = Account.create_with_mnemonic(); print(m)\""
        )
    return seed


def derive_wallet(index: int) -> tuple[str, str]:
    """
    Derive (address, private_key) for a given HD index.
    Index 0 = oracle. Index 1+ = merchants.
    """
    seed = _get_master_seed()
    path = f"{_DERIVATION_BASE}/{index}"
    acct = Account.from_mnemonic(seed, account_path=path)
    return acct.address, acct.key.hex()


def derive_oracle_wallet() -> tuple[str, str]:
    return derive_wallet(ORACLE_INDEX)


def get_oracle_address() -> str:
    addr, _ = derive_oracle_wallet()
    return addr


async def assign_sovereign_wallet(merchant_id: str) -> dict:
    """
    Assign an HD-derived wallet to a merchant if they don't have one.
    Idempotent — safe to call multiple times.

    Returns {"wallet_address": "0x...", "wallet_index": N, "newly_assigned": bool}
    """
    from services.supabase_service import get_client, get_merchant_by_id, update_merchant

    merchant = await get_merchant_by_id(merchant_id)
    if not merchant:
        raise ValueError(f"Merchant {merchant_id} not found")

    # Already has a sovereign wallet
    if merchant.get("wallet_index") is not None:
        return {
            "wallet_address": merchant["wallet_address"],
            "wallet_index": merchant["wallet_index"],
            "newly_assigned": False,
        }

    # Claim the next available index (atomic via DB)
    client = get_client()
    index_row = client.rpc("claim_next_wallet_index", {}).execute()
    index = index_row.data

    address, _ = derive_wallet(index)

    await update_merchant(merchant_id, {
        "wallet_address": address,
        "wallet_index": index,
    })

    logger.info("[Wallet] Merchant %s assigned wallet index %d → %s", merchant_id, index, address)
    return {
        "wallet_address": address,
        "wallet_index": index,
        "newly_assigned": True,
    }


def get_merchant_address(wallet_index: int) -> str:
    """Derive a merchant's wallet address from their stored index."""
    addr, _ = derive_wallet(wallet_index)
    return addr


def sign_transaction_as_merchant(wallet_index: int, transaction: dict) -> str:
    """
    Sign a transaction with a merchant's sovereign key.
    Returns the raw signed transaction hex for broadcasting.
    Used for ERC-20 permit / approval flows.
    """
    _, private_key = derive_wallet(wallet_index)
    signed = Account.sign_transaction(transaction, private_key=private_key)
    return signed.raw_transaction.hex()


def generate_new_master_seed() -> str:
    """
    Generate a fresh 24-word BIP-39 mnemonic.
    Call once during initial setup — BACK IT UP IMMEDIATELY.
    """
    _, mnemonic = Account.create_with_mnemonic(num_words=24)
    return mnemonic
