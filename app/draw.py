"""One-shot weekly draw command, intended to run from a scheduler."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime

from app.config import TICKET_PRICE_BASE_UNITS, ZERO_ADDRESS, settings
from app.lottery import previous_period_end, select_winner
from app.payout import send_payout
from app.rpc import TempoRpc
from app.store import LotteryStore

logger = logging.getLogger(__name__)


async def retry_latest_failed_payout() -> dict:
    """Retry the newest failed payout without selecting a different winner."""
    store = LotteryStore(settings.database_path)
    draw = store.latest_failed_draw()
    if draw is None:
        return {"action": "skipped", "reason": "no failed payout"}
    if not draw.winner:
        raise RuntimeError("failed draw has no winner")
    if settings.payment_destination == ZERO_ADDRESS:
        raise RuntimeError("PAYMENT_DESTINATION is not configured")

    try:
        payout_tx = await asyncio.to_thread(
            send_payout,
            rpc_url=settings.rpc_url,
            expected_sender=settings.payment_destination,
            winner=draw.winner,
            amount=draw.payout_amount,
        )
    except Exception as exc:
        logger.exception("payout retry failed period_end=%s winner=%s", draw.period_end, draw.winner)
        failed = store.mark_failed(draw.period_end, str(exc))
        return {"action": "failed", "retry": True, "draw": failed.as_dict()}

    paid = store.mark_paid(draw.period_end, payout_tx)
    return {"action": "paid", "retry": True, "draw": paid.as_dict()}


async def run_draw(now: int | None = None, *, dry_run: bool = False) -> dict:
    if not settings.lottery_enabled and not dry_run:
        return {"action": "skipped", "reason": "lottery is not enabled"}
    current = now if now is not None else int(datetime.now(UTC).timestamp())
    period_end = previous_period_end(
        current + 1, settings.draw_weekday_utc, settings.draw_hour_utc,
        settings.draw_minute_utc, settings.draw_second_utc,
    )
    store = LotteryStore(settings.database_path)
    existing = next(
        (draw for draw in store.latest_draws(100) if draw.period_end == period_end), None
    )
    if existing:
        return {"action": "skipped", "reason": "draw already exists", "draw": existing.as_dict()}

    tickets = store.tickets_for_period(period_end)
    if not tickets:
        return {"action": "skipped", "reason": "no tickets", "period_end": period_end}
    if any(ticket.amount != TICKET_PRICE_BASE_UNITS for ticket in tickets):
        raise RuntimeError("period contains a ticket with an unexpected payment amount")

    block_number, block_hash = await TempoRpc(settings.rpc_url).block_at_or_after(period_end)
    winner_ticket, seed, winner_index = select_winner(
        tickets, period_end=period_end, block_hash=block_hash
    )
    pool = sum(ticket.amount for ticket in tickets)
    payout = pool * settings.payout_bps // 10_000

    if dry_run:
        return {
            "action": "dry-run",
            "period_end": period_end,
            "ticket_count": len(tickets),
            "pool_amount": pool,
            "payout_amount": payout,
            "winner": winner_ticket.payer,
            "winner_index": winner_index,
            "randomness_block": block_number,
            "randomness_hash": block_hash,
            "seed": seed,
        }

    if settings.payment_destination == ZERO_ADDRESS:
        raise RuntimeError("PAYMENT_DESTINATION is not configured")

    draw, created = store.create_selected_draw(
        period_end=period_end,
        ticket_count=len(tickets),
        pool_amount=pool,
        payout_amount=payout,
        winner=winner_ticket.payer,
        winner_ticket_id=winner_ticket.id,
        randomness_block=block_number,
        randomness_hash=block_hash,
        seed=seed,
    )
    if not created:
        return {"action": "skipped", "reason": "draw claimed by another worker", "draw": draw.as_dict()}

    try:
        payout_tx = await asyncio.to_thread(
            send_payout,
            rpc_url=settings.rpc_url,
            expected_sender=settings.payment_destination,
            winner=winner_ticket.payer,
            amount=payout,
        )
    except Exception as exc:
        logger.exception("payout failed period_end=%s winner=%s", period_end, winner_ticket.payer)
        failed = store.mark_failed(period_end, str(exc))
        return {"action": "failed", "draw": failed.as_dict()}

    paid = store.mark_paid(period_end, payout_tx)
    return {"action": "paid", "draw": paid.as_dict()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the latest due Tempo lottery draw once")
    parser.add_argument("--dry-run", action="store_true", help="select without recording or paying")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_draw(dry_run=args.dry_run)), indent=2))


if __name__ == "__main__":
    main()
