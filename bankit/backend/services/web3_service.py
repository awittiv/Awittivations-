import os
import json
import hashlib
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
ORACLE_PUBLIC_KEY = os.getenv("ORACLE_PUBLIC_KEY", "0x0000000000000000000000000000000000000000")
ORACLE_PRIVATE_KEY = os.getenv("ORACLE_PRIVATE_KEY", "0x" + "0" * 64)
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")
PASSPORT_ADDRESS = os.getenv("PASSPORT_ADDRESS", "0x0000000000000000000000000000000000000000")

_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
if CONTRACT_ADDRESS == _ZERO_ADDRESS:
    logger.warning(
        "[Web3] CONTRACT_ADDRESS is not set — all on-chain disbursements will fail silently. "
        "Deploy BankitLiquidityRouter and set CONTRACT_ADDRESS in your environment."
    )
if PASSPORT_ADDRESS == _ZERO_ADDRESS:
    logger.warning(
        "[Web3] PASSPORT_ADDRESS is not set — credit passport minting will be skipped. "
        "Deploy BankitCreditPassport and set PASSPORT_ADDRESS in your environment."
    )
if ORACLE_PUBLIC_KEY == _ZERO_ADDRESS or ORACLE_PRIVATE_KEY == "0x" + "0" * 64:
    logger.warning(
        "[Web3] ORACLE_PUBLIC_KEY / ORACLE_PRIVATE_KEY are not set — transactions cannot be signed."
    )

# ABI for BankitLiquidityRouter — releaseMicroLiquidity (disburse) + repayLoan
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"recipientWallet","type":"address"},{"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"internalType":"string","name":"trustScoreHash","type":"string"}],"name":"releaseMicroLiquidity","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"from","type":"address"},{"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"internalType":"string","name":"loanId","type":"string"}],"name":"repayLoan","outputs":[],"stateMutability":"nonpayable","type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"recipient","type":"address"},{"indexed":false,"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"indexed":false,"internalType":"string","name":"trustScoreHash","type":"string"}],"name":"MicroLiquidityReleased","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"from","type":"address"},{"indexed":false,"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"indexed":false,"internalType":"string","name":"loanId","type":"string"}],"name":"LoanRepaid","type":"event"}]')

# ABI for BankitCreditPassport — mintPassport + updateCreditProfile
PASSPORT_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"merchantWallet","type":"address"},{"internalType":"string","name":"merchantId","type":"string"},{"internalType":"uint8","name":"initialScore","type":"uint8"}],"name":"mintPassport","outputs":[{"internalType":"uint256","name":"tokenId","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"merchantId","type":"string"},{"internalType":"uint8","name":"newScore","type":"uint8"},{"internalType":"bool","name":"loanRepaid","type":"bool"},{"internalType":"uint96","name":"repaidUnits","type":"uint96"}],"name":"updateCreditProfile","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"wallet","type":"address"}],"name":"creditScore","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"wallet","type":"address"}],"name":"hasPassport","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"","type":"string"}],"name":"merchantTokenId","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"tokenId","type":"uint256"},{"indexed":true,"internalType":"address","name":"wallet","type":"address"},{"internalType":"string","name":"merchantId","type":"string"}],"name":"PassportMinted","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"tokenId","type":"uint256"},{"internalType":"uint8","name":"newScore","type":"uint8"},{"internalType":"uint32","name":"loansRepaid","type":"uint32"}],"name":"CreditProfileUpdated","type":"event"}]')

_web3: Web3 | None = None


def get_web3() -> Web3:
    global _web3
    if _web3 is None:
        _web3 = Web3(Web3.HTTPProvider(RPC_URL))
    return _web3


def build_trust_score_hash(loan_id: str, score: int, reasoning: str) -> str:
    payload = f"{loan_id}:{score}:{reasoning}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_contract():
    web3 = get_web3()
    return web3.eth.contract(address=CONTRACT_ADDRESS, abi=ROUTER_ABI)


async def _send_transaction(fn) -> str | None:
    web3 = get_web3()

    if not web3.is_connected():
        logger.error("Cannot connect to blockchain network — RPC: %s", RPC_URL)
        return None

    try:
        nonce = web3.eth.get_transaction_count(ORACLE_PUBLIC_KEY)
        transaction = fn.build_transaction({
            "chainId": 137,
            "gas": 200000,
            "maxFeePerGas": web3.to_wei("50", "gwei"),
            "maxPriorityFeePerGas": web3.to_wei("30", "gwei"),
            "nonce": nonce,
        })
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=ORACLE_PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        return web3.to_hex(tx_hash)
    except Exception as e:
        logger.error("Transaction failed: %s", e)
        return None


async def release_micro_liquidity(
    recipient_wallet: str,
    amount_inr: float,
    trust_score_hash: str,
) -> str | None:
    contract = _get_contract()
    amount_in_units = int(amount_inr * (10 ** 6))
    fn = contract.functions.releaseMicroLiquidity(
        recipient_wallet,
        amount_in_units,
        trust_score_hash,
    )
    return await _send_transaction(fn)


async def repay_loan_onchain(
    merchant_wallet: str,
    amount_inr: float,
    loan_id: str,
) -> str | None:
    """Burn BKD from merchant wallet on-chain when a loan is repaid."""
    contract = _get_contract()
    amount_in_units = int(amount_inr * (10 ** 6))
    fn = contract.functions.repayLoan(
        merchant_wallet,
        amount_in_units,
        loan_id,
    )
    return await _send_transaction(fn)


# ── Credit Passport ──────────────────────────────────────────────────────────

def _get_passport_contract():
    web3 = get_web3()
    return web3.eth.contract(address=PASSPORT_ADDRESS, abi=PASSPORT_ABI)


async def mint_credit_passport(
    merchant_wallet: str,
    merchant_id: str,
    initial_score: int,
) -> str | None:
    """Mint a soulbound BankitCreditPassport NFT to the merchant's wallet."""
    if PASSPORT_ADDRESS == _ZERO_ADDRESS:
        logger.warning("[Passport] PASSPORT_ADDRESS not set — skipping mint")
        return None
    contract = _get_passport_contract()
    fn = contract.functions.mintPassport(
        merchant_wallet,
        merchant_id,
        max(0, min(100, initial_score)),
    )
    return await _send_transaction(fn)


async def update_credit_passport(
    merchant_id: str,
    new_score: int,
    loan_repaid: bool,
    repaid_amount_inr: float = 0.0,
) -> str | None:
    """Update the merchant's on-chain credit profile after a loan event."""
    if PASSPORT_ADDRESS == _ZERO_ADDRESS:
        return None
    contract = _get_passport_contract()
    repaid_units = int(repaid_amount_inr * (10 ** 6))
    fn = contract.functions.updateCreditProfile(
        merchant_id,
        max(0, min(100, new_score)),
        loan_repaid,
        repaid_units,
    )
    return await _send_transaction(fn)


def get_passport_token_id(merchant_id: str) -> int | None:
    """Synchronous read — returns on-chain token ID for a merchant, or None."""
    if PASSPORT_ADDRESS == _ZERO_ADDRESS:
        return None
    try:
        contract = _get_passport_contract()
        token_id = contract.functions.merchantTokenId(merchant_id).call()
        return token_id if token_id != 0 else None
    except Exception as exc:
        logger.warning("[Passport] Could not read tokenId for %s: %s", merchant_id, exc)
        return None
