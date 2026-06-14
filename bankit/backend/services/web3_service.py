import os
import json
import hashlib
from web3 import Web3

RPC_URL = os.getenv("POLYGON_RPC_URL", "https://rpc-amoy.polygon.technology")
ORACLE_PUBLIC_KEY = os.getenv("ORACLE_PUBLIC_KEY", "0x0000000000000000000000000000000000000000")
ORACLE_PRIVATE_KEY = os.getenv("ORACLE_PRIVATE_KEY", "0x" + "0" * 64)
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")

# ABI for BankitLiquidityRouter — the oracle calls releaseMicroLiquidity (disburse)
# and repayLoan (on-chain repayment recording).
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"address","name":"recipientWallet","type":"address"},{"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"internalType":"string","name":"trustScoreHash","type":"string"}],"name":"releaseMicroLiquidity","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"from","type":"address"},{"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"internalType":"string","name":"loanId","type":"string"}],"name":"repayLoan","outputs":[],"stateMutability":"nonpayable","type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"recipient","type":"address"},{"indexed":false,"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"indexed":false,"internalType":"string","name":"trustScoreHash","type":"string"}],"name":"MicroLiquidityReleased","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"from","type":"address"},{"indexed":false,"internalType":"uint256","name":"fiatAmount","type":"uint256"},{"indexed":false,"internalType":"string","name":"loanId","type":"string"}],"name":"LoanRepaid","type":"event"}]')

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
        print("[Web3] Cannot connect to blockchain network.")
        return None

    try:
        nonce = web3.eth.get_transaction_count(ORACLE_PUBLIC_KEY)
        transaction = fn.build_transaction({
            "chainId": 80002,
            "gas": 200000,
            "maxFeePerGas": web3.to_wei("2", "gwei"),
            "maxPriorityFeePerGas": web3.to_wei("1", "gwei"),
            "nonce": nonce,
        })
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=ORACLE_PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        return web3.to_hex(tx_hash)
    except Exception as e:
        print(f"[Web3] Transaction failed: {e}")
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
