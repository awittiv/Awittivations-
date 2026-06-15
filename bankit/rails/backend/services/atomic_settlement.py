import os
import json
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

RPC_URL            = os.getenv("POLYGON_RPC_URL", "https://rpc-amoy.polygon.technology")
ATTESTER_ADDRESS   = os.getenv("RAILS_ATTESTER_ADDRESS", "0x" + "0" * 40)
ATTESTER_KEY       = os.getenv("RAILS_ATTESTER_PRIVATE_KEY", "0x" + "0" * 64)
COMPLIANCE_ADDRESS = os.getenv("COMPLIANCE_ATTESTATION_ADDRESS", "0x" + "0" * 40)
DISBURSEMENT_ADDRESS = os.getenv("ATOMIC_DISBURSEMENT_ADDRESS", "0x" + "0" * 40)
VAULT_ADDRESS      = os.getenv("RAILS_VAULT_ADDRESS", "0x" + "0" * 40)

CHAIN_ID = 80002  # Polygon Amoy testnet

_ZERO = "0x" + "0" * 40
for _name, _val in [
    ("RAILS_ATTESTER_ADDRESS",          ATTESTER_ADDRESS),
    ("COMPLIANCE_ATTESTATION_ADDRESS",  COMPLIANCE_ADDRESS),
    ("ATOMIC_DISBURSEMENT_ADDRESS",     DISBURSEMENT_ADDRESS),
    ("RAILS_VAULT_ADDRESS",             VAULT_ADDRESS),
]:
    if _val == _ZERO:
        logger.warning(f"[Rails] {_name} not set — deploy contracts and configure env.")

COMPLIANCE_ABI = json.loads('[{"inputs":[{"internalType":"bytes32","name":"complianceHash","type":"bytes32"},{"internalType":"bytes32","name":"projectId","type":"bytes32"},{"internalType":"uint8","name":"programType","type":"uint8"},{"internalType":"uint8","name":"nsfiPillar","type":"uint8"},{"internalType":"string","name":"applicationRef","type":"string"},{"internalType":"uint256","name":"amountUSDCents","type":"uint256"}],"name":"attest","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"complianceHash","type":"bytes32"}],"name":"isAttested","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"complianceHash","type":"bytes32"}],"name":"revoke","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"attestations","outputs":[{"internalType":"bytes32","name":"complianceHash","type":"bytes32"},{"internalType":"bytes32","name":"projectId","type":"bytes32"},{"internalType":"uint8","name":"programType","type":"uint8"},{"internalType":"uint8","name":"nsfiPillar","type":"uint8"},{"internalType":"string","name":"applicationRef","type":"string"},{"internalType":"uint256","name":"amountUSDCents","type":"uint256"},{"internalType":"uint256","name":"attestedAt","type":"uint256"},{"internalType":"address","name":"attester","type":"address"},{"internalType":"bool","name":"active","type":"bool"}],"stateMutability":"view","type":"function"}]')

_web3: Web3 | None = None


def _w3() -> Web3:
    global _web3
    if _web3 is None:
        _web3 = Web3(Web3.HTTPProvider(RPC_URL))
    return _web3


async def _send_tx(fn) -> str | None:
    web3 = _w3()
    if not web3.is_connected():
        logger.error("[Rails] Cannot connect to Polygon node")
        return None
    try:
        nonce = web3.eth.get_transaction_count(ATTESTER_ADDRESS)
        tx = fn.build_transaction({
            "chainId":              CHAIN_ID,
            "gas":                  300_000,
            "maxFeePerGas":         web3.to_wei("30", "gwei"),
            "maxPriorityFeePerGas": web3.to_wei("25", "gwei"),
            "nonce":                nonce,
        })
        signed = web3.eth.account.sign_transaction(tx, private_key=ATTESTER_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        return web3.to_hex(tx_hash)
    except Exception as e:
        logger.error(f"[Rails] Transaction failed: {e}")
        return None


async def write_compliance_attestation(
    compliance_hash_hex: str,
    project_id_hex: str,
    program_type: int,
    nsfi_pillar: int,
    application_ref: str,
    amount_usd_cents: int,
) -> str | None:
    web3 = _w3()
    contract = web3.eth.contract(address=COMPLIANCE_ADDRESS, abi=COMPLIANCE_ABI)

    c_hash = bytes.fromhex(compliance_hash_hex.removeprefix("0x"))
    p_id   = bytes.fromhex(project_id_hex.removeprefix("0x"))

    fn = contract.functions.attest(
        c_hash, p_id, program_type, nsfi_pillar, application_ref, amount_usd_cents
    )
    return await _send_tx(fn)


async def revoke_attestation(compliance_hash_hex: str) -> str | None:
    web3 = _w3()
    contract = web3.eth.contract(address=COMPLIANCE_ADDRESS, abi=COMPLIANCE_ABI)
    c_hash = bytes.fromhex(compliance_hash_hex.removeprefix("0x"))
    return await _send_tx(contract.functions.revoke(c_hash))


async def is_attested(compliance_hash_hex: str) -> bool:
    if not compliance_hash_hex or compliance_hash_hex == "0x":
        return False
    web3 = _w3()
    if not web3.is_connected():
        return False
    try:
        contract = web3.eth.contract(address=COMPLIANCE_ADDRESS, abi=COMPLIANCE_ABI)
        c_hash = bytes.fromhex(compliance_hash_hex.removeprefix("0x"))
        return contract.functions.isAttested(c_hash).call()
    except Exception as e:
        logger.error(f"[Rails] isAttested check failed: {e}")
        return False
