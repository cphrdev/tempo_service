"""Create and broadcast a TIP-20 payout transaction on Tempo."""

from __future__ import annotations

import os

from eth_account import Account
from pytempo import TempoTransaction
from pytempo.contracts import TIP20
from web3 import Web3

from app.config import CHAIN_ID, USDC_E


def send_payout(*, rpc_url: str, expected_sender: str, winner: str, amount: int) -> str:
    private_key = os.getenv("LOTTERY_PAYOUT_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("LOTTERY_PAYOUT_PRIVATE_KEY is not configured")

    account = Account.from_key(private_key)
    if account.address.lower() != expected_sender.lower():
        raise RuntimeError("payout key does not match PAYMENT_DESTINATION")

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        raise RuntimeError("cannot connect to Tempo RPC")
    if w3.eth.chain_id != CHAIN_ID:
        raise RuntimeError(f"RPC returned chain {w3.eth.chain_id}, expected {CHAIN_ID}")

    # nonce_key=0 is Tempo's standard protocol nonce. The Nonce precompile is
    # only for parallel lanes (nonce_key >= 1), and rejects protocol nonce
    # queries with ProtocolNonceNotSupported.
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    gas_price = int(w3.eth.gas_price)
    transaction = TempoTransaction.create(
        chain_id=CHAIN_ID,
        gas_limit=100_000,
        max_fee_per_gas=max(gas_price * 2, 1),
        max_priority_fee_per_gas=gas_price,
        nonce=nonce,
        nonce_key=0,
        fee_token=USDC_E,
        calls=(TIP20(USDC_E).transfer(to=winner, amount=amount),),
    ).sign(private_key)

    tx_hash = w3.eth.send_raw_transaction(transaction.encode())
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"payout transaction reverted: {tx_hash.hex()}")
    return "0x" + tx_hash.hex().removeprefix("0x")
