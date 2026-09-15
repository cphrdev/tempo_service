"""MPP-paid Tempo lottery API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mpp import Challenge
from mpp.methods.tempo import ChargeIntent, tempo
from mpp.server import Mpp

from app.config import (
    CHAIN_ID,
    TICKET_PRICE,
    TICKET_PRICE_BASE_UNITS,
    USDC_DECIMALS,
    ZERO_ADDRESS,
    settings,
)
from app.lottery import next_period_end, payer_address
from app.store import LotteryStore

store = LotteryStore(settings.database_path)
payment_server = Mpp.create(
    method=tempo(
        chain_id=CHAIN_ID,
        currency=settings.payment_currency,
        recipient=settings.payment_destination,
        intents={"charge": ChargeIntent()},
    )
)

app = FastAPI(
    title="Tempo Weekly Lottery API",
    version="1.0.0",
    description="One 0.05 USDC.e ticket per MPP-paid request; weekly verifiable draw.",
)


def amount(value: int) -> str:
    return f"{value / 10**USDC_DECIMALS:.{USDC_DECIMALS}f}"


@app.get("/")
async def index():
    return {
        "service": "Tempo Weekly Lottery",
        "enabled": settings.lottery_enabled,
        "ticket_price": f"{TICKET_PRICE} USDC.e",
        "payout": f"{settings.payout_bps / 100:.2f}% of each weekly pool",
        "paid_endpoint": "POST /v1/lottery/enter",
        "status_endpoint": "GET /v1/lottery/status",
        "draws_endpoint": "GET /v1/lottery/draws",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "chain_id": CHAIN_ID}


@app.get("/v1/lottery/status")
async def lottery_status():
    now = int(datetime.now(UTC).timestamp())
    period_end = next_period_end(now, settings.draw_weekday_utc, settings.draw_hour_utc)
    stats = store.period_stats(period_end)
    return {
        "period_end": period_end,
        "period_end_iso": datetime.fromtimestamp(period_end, UTC).isoformat(),
        "ticket_price": TICKET_PRICE,
        "ticket_count": stats["ticket_count"],
        "pool": amount(stats["pool_amount"]),
        "projected_payout": amount(stats["pool_amount"] * settings.payout_bps // 10_000),
        "currency": "USDC.e",
    }


@app.get("/v1/lottery/draws")
async def lottery_draws():
    return {"draws": [draw.as_dict() for draw in store.latest_draws()]}


@app.post("/v1/lottery/enter")
async def enter_lottery(request: Request):
    if not settings.lottery_enabled:
        return JSONResponse(
            status_code=503,
            content={"error": "Lottery is not enabled"},
        )
    if settings.payment_destination == ZERO_ADDRESS:
        return JSONResponse(
            status_code=503,
            content={"error": "PAYMENT_DESTINATION is not configured"},
        )

    payment = await payment_server.charge(
        authorization=request.headers.get("Authorization"),
        amount=TICKET_PRICE,
        chain_id=CHAIN_ID,
    )
    if isinstance(payment, Challenge):
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required", "price": TICKET_PRICE, "currency": "USDC.e"},
            headers={"WWW-Authenticate": payment.to_www_authenticate(payment_server.realm)},
        )

    credential, receipt = payment
    now = int(datetime.now(UTC).timestamp())
    period_end = next_period_end(now, settings.draw_weekday_utc, settings.draw_hour_utc)
    try:
        payer = payer_address(credential.source)
        ticket, created = store.add_ticket(
            period_end=period_end,
            payer=payer,
            payment_tx=receipt.reference,
            amount=TICKET_PRICE_BASE_UNITS,
            created_at=now,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "verified payment could not be recorded", "detail": str(exc)},
        )

    response = {
        "ticket": asdict(ticket),
        "created": created,
        "period_end_iso": datetime.fromtimestamp(period_end, UTC).isoformat(),
        "payment": {"payer": payer, "reference": receipt.reference, "amount": TICKET_PRICE},
    }
    return JSONResponse(
        content=response,
        headers={"Payment-Receipt": receipt.to_payment_receipt()},
    )
