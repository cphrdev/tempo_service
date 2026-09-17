"""Period calculation, payer parsing, and verifiable winner selection."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from app.store import Ticket


def next_period_end(timestamp: int, weekday: int, hour: int, minute: int = 0, second: int = 0) -> int:
    current = datetime.fromtimestamp(timestamp, UTC)
    days = (weekday - current.weekday()) % 7
    candidate = current.replace(
        hour=hour, minute=minute, second=second, microsecond=0
    ) + timedelta(days=days)
    if candidate <= current:
        candidate += timedelta(days=7)
    return int(candidate.timestamp())


def previous_period_end(
    timestamp: int, weekday: int, hour: int, minute: int = 0, second: int = 0
) -> int:
    return next_period_end(timestamp, weekday, hour, minute, second) - 7 * 24 * 60 * 60


def payer_address(source: str) -> str:
    candidate = source.rsplit(":", 1)[-1]
    if not candidate.startswith("0x") or len(candidate) != 42:
        raise ValueError("MPP payer source does not contain an EVM address")
    int(candidate[2:], 16)
    return candidate.lower()


def select_winner(
    tickets: list[Ticket], *, period_end: int, block_hash: str
) -> tuple[Ticket, str, int]:
    if not tickets:
        raise ValueError("cannot select a winner without tickets")
    ordered = sorted(tickets, key=lambda ticket: (ticket.payment_tx, ticket.id))
    material = "|".join(
        ["tempo-lottery-v1", str(period_end), block_hash.lower()]
        + [ticket.payment_tx.lower() for ticket in ordered]
    )
    seed = "0x" + hashlib.sha256(material.encode()).hexdigest()
    index = int(seed[2:], 16) % len(ordered)
    return ordered[index], seed, index
