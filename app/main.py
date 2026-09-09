"""FastAPI application exposing an MPP-paid Tempo transaction preflight."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mpp import Challenge
from mpp.methods.tempo import ChargeIntent, tempo
from mpp.server import Mpp
from pydantic import BaseModel, Field, field_validator

from app.analyzer import decode_call, risk_assessment

CHAIN_ID = 4217
PRICE_USDC = "0.01"
USDC_E = "0x20C000000000000000000000b9537d11c60E8b50"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

RPC_URL = os.getenv("TEMPO_RPC_URL", "https://rpc.tempo.xyz")
PAYMENT_DESTINATION = os.getenv("PAYMENT_DESTINATION", ZERO_ADDRESS)
PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", USDC_E)

payment_server = Mpp.create(
    method=tempo(
        chain_id=CHAIN_ID,
        currency=PAYMENT_CURRENCY,
        recipient=PAYMENT_DESTINATION,
        intents={"charge": ChargeIntent()},
    )
)

app = FastAPI(
    title="Tempo Preflight API",
    version="0.1.0",
    description="Payment-gated, read-only transaction simulation and risk analysis for Tempo.",
)


class TransactionInput(BaseModel):
    sender: str = Field(alias="from")
    to: str
    value: str = "0x0"
    data: str = "0x"

    model_config = {"populate_by_name": True}

    @field_validator("sender", "to")
    @classmethod
    def validate_address(cls, value: str) -> str:
        if not value.startswith("0x") or len(value) != 42:
            raise ValueError("must be a 20-byte 0x-prefixed address")
        int(value[2:], 16)
        return value

    @field_validator("value", "data")
    @classmethod
    def validate_hex(cls, value: str) -> str:
        if not value.startswith("0x"):
            raise ValueError("must be 0x-prefixed hex")
        int(value[2:] or "0", 16)
        return value


async def rpc(method: str, params: list[Any]) -> Any:
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        response.raise_for_status()
        payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message", "Tempo RPC error"))
    return payload["result"]


@app.get("/")
async def index():
    return {
        "service": "Tempo Preflight API",
        "price": f"{PRICE_USDC} USDC.e per analysis",
        "paid_endpoint": "POST /v1/transaction/preflight",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "chain_id": CHAIN_ID}


@app.post("/v1/transaction/preflight")
async def preflight(transaction: TransactionInput, request: Request):
    if PAYMENT_DESTINATION == ZERO_ADDRESS:
        return JSONResponse(
            status_code=503,
            content={"error": "PAYMENT_DESTINATION is not configured"},
        )

    payment = await payment_server.charge(
        authorization=request.headers.get("Authorization"),
        amount=PRICE_USDC,
        chain_id=CHAIN_ID,
    )
    if isinstance(payment, Challenge):
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required", "price": PRICE_USDC, "currency": "USDC.e"},
            headers={"WWW-Authenticate": payment.to_www_authenticate(payment_server.realm)},
        )

    credential, receipt = payment
    tx = transaction.model_dump(by_alias=True)
    decoded = decode_call(transaction.data)

    try:
        chain_hex, block_hex, code = await _rpc_context(transaction.to)
        actual_chain_id = int(chain_hex, 16)
        if actual_chain_id != CHAIN_ID:
            raise RuntimeError(f"RPC returned chain {actual_chain_id}, expected {CHAIN_ID}")

        estimate_result, call_result = await _simulate(tx)
        simulation_ok = call_result[0]
        target_is_contract = code not in ("0x", "0x0", None)
        verdict, warnings = risk_assessment(decoded, simulation_ok, target_is_contract)
        result = {
            "verdict": verdict,
            "warnings": warnings,
            "simulation": {
                "success": simulation_ok,
                "return_data": call_result[1] if simulation_ok else None,
                "error": None if simulation_ok else call_result[1],
                "estimated_gas": int(estimate_result[1], 16) if estimate_result[0] else None,
                "gas_error": None if estimate_result[0] else estimate_result[1],
            },
            "target": {"address": transaction.to, "is_contract": target_is_contract},
            "decoded_call": (
                {"function": decoded.function, "arguments": decoded.arguments} if decoded else None
            ),
            "chain": {"id": actual_chain_id, "block_number": int(block_hex, 16)},
            "payment": {"payer": credential.source, "reference": receipt.reference, "amount": PRICE_USDC},
            "disclaimer": "Heuristic analysis only; a safe verdict is not a security guarantee.",
        }
        return JSONResponse(content=result, headers={"Payment-Receipt": receipt.to_payment_receipt()})
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": "Tempo RPC analysis failed", "detail": str(exc)})


async def _rpc_context(target: str) -> tuple[str, str, str]:
    import asyncio

    chain, block, code = await asyncio.gather(
        rpc("eth_chainId", []),
        rpc("eth_blockNumber", []),
        rpc("eth_getCode", [target, "latest"]),
    )
    return chain, block, code


async def _simulate(tx: dict[str, str]) -> tuple[tuple[bool, str], tuple[bool, str]]:
    import asyncio

    async def capture(method: str) -> tuple[bool, str]:
        try:
            return True, await rpc(method, [tx, "latest"])
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            return False, str(exc)

    estimate, call = await asyncio.gather(capture("eth_estimateGas"), capture("eth_call"))
    return estimate, call

