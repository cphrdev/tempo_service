"""Persistent ticket and draw ledger backed by SQLite."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Ticket:
    id: int
    period_end: int
    payer: str
    payment_tx: str
    amount: int
    created_at: int


@dataclass(frozen=True)
class Draw:
    period_end: int
    status: str
    ticket_count: int
    pool_amount: int
    payout_amount: int
    winner: str | None
    winner_ticket_id: int | None
    randomness_block: int | None
    randomness_hash: str | None
    seed: str | None
    payout_tx: str | None
    error: str | None
    created_at: int
    updated_at: int

    def as_dict(self) -> dict:
        return asdict(self)


class LotteryStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_end INTEGER NOT NULL,
                    payer TEXT NOT NULL,
                    payment_tx TEXT NOT NULL UNIQUE,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tickets_period_idx ON tickets(period_end, id);
                CREATE TABLE IF NOT EXISTS draws (
                    period_end INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    ticket_count INTEGER NOT NULL,
                    pool_amount INTEGER NOT NULL,
                    payout_amount INTEGER NOT NULL,
                    winner TEXT,
                    winner_ticket_id INTEGER,
                    randomness_block INTEGER,
                    randomness_hash TEXT,
                    seed TEXT,
                    payout_tx TEXT,
                    error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(winner_ticket_id) REFERENCES tickets(id)
                );
                """
            )
            db.commit()

    def add_ticket(
        self,
        *,
        period_end: int,
        payer: str,
        payment_tx: str,
        amount: int,
        created_at: int | None = None,
    ) -> tuple[Ticket, bool]:
        now = created_at or int(datetime.now(UTC).timestamp())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM tickets WHERE payment_tx = ?", (payment_tx,)
            ).fetchone()
            if existing:
                db.commit()
                return Ticket(**dict(existing)), False
            cursor = db.execute(
                """INSERT INTO tickets(period_end, payer, payment_tx, amount, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (period_end, payer.lower(), payment_tx.lower(), amount, now),
            )
            row = db.execute("SELECT * FROM tickets WHERE id = ?", (cursor.lastrowid,)).fetchone()
            db.commit()
            return Ticket(**dict(row)), True

    def tickets_for_period(self, period_end: int) -> list[Ticket]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM tickets WHERE period_end = ? ORDER BY payment_tx, id",
                (period_end,),
            ).fetchall()
        return [Ticket(**dict(row)) for row in rows]

    def period_stats(self, period_end: int) -> dict[str, int]:
        with self.connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS ticket_count, COALESCE(SUM(amount), 0) AS pool_amount
                   FROM tickets WHERE period_end = ?""",
                (period_end,),
            ).fetchone()
        return dict(row)

    def create_selected_draw(
        self,
        *,
        period_end: int,
        ticket_count: int,
        pool_amount: int,
        payout_amount: int,
        winner: str,
        winner_ticket_id: int,
        randomness_block: int,
        randomness_hash: str,
        seed: str,
    ) -> tuple[Draw, bool]:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM draws WHERE period_end = ?", (period_end,)
            ).fetchone()
            if existing:
                db.commit()
                return Draw(**dict(existing)), False
            db.execute(
                """INSERT INTO draws(
                       period_end, status, ticket_count, pool_amount, payout_amount,
                       winner, winner_ticket_id, randomness_block, randomness_hash,
                       seed, payout_tx, error, created_at, updated_at
                   ) VALUES (?, 'selected', ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                (
                    period_end,
                    ticket_count,
                    pool_amount,
                    payout_amount,
                    winner.lower(),
                    winner_ticket_id,
                    randomness_block,
                    randomness_hash,
                    seed,
                    now,
                    now,
                ),
            )
            row = db.execute("SELECT * FROM draws WHERE period_end = ?", (period_end,)).fetchone()
            db.commit()
        return Draw(**dict(row)), True

    def mark_paid(self, period_end: int, payout_tx: str) -> Draw:
        return self._update_draw(period_end, "paid", payout_tx=payout_tx.lower(), error=None)

    def mark_failed(self, period_end: int, error: str) -> Draw:
        return self._update_draw(period_end, "failed", payout_tx=None, error=error[:1000])

    def _update_draw(
        self, period_end: int, status: str, *, payout_tx: str | None, error: str | None
    ) -> Draw:
        now = int(datetime.now(UTC).timestamp())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE draws SET status = ?, payout_tx = ?, error = ?, updated_at = ?
                   WHERE period_end = ?""",
                (status, payout_tx, error, now, period_end),
            )
            row = db.execute("SELECT * FROM draws WHERE period_end = ?", (period_end,)).fetchone()
            db.commit()
        if row is None:
            raise ValueError("draw not found")
        return Draw(**dict(row))

    def latest_draws(self, limit: int = 20) -> list[Draw]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM draws ORDER BY period_end DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Draw(**dict(row)) for row in rows]

    def latest_failed_draw(self) -> Draw | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM draws WHERE status = 'failed' ORDER BY period_end DESC LIMIT 1"
            ).fetchone()
        return Draw(**dict(row)) if row else None
