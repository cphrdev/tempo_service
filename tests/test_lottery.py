from app.lottery import next_period_end, payer_address, select_winner
from app.store import LotteryStore


def test_next_period_end_is_strictly_future():
    sunday_20_utc = 1_789_329_600
    assert next_period_end(sunday_20_utc, 6, 20) == sunday_20_utc + 7 * 24 * 60 * 60


def test_payer_address_accepts_did():
    address = "0x12F926EFfC5397bd60991862FAB5F3179EC9db28"
    assert payer_address(f"did:pkh:eip155:4217:{address}") == address.lower()


def test_ticket_payment_is_idempotent(tmp_path):
    store = LotteryStore(str(tmp_path / "lottery.db"))
    values = dict(
        period_end=2_000_000_000,
        payer="0x1111111111111111111111111111111111111111",
        payment_tx="0x" + "ab" * 32,
        amount=50_000,
        created_at=1_999_999_000,
    )
    first, first_created = store.add_ticket(**values)
    second, second_created = store.add_ticket(**values)
    assert first.id == second.id
    assert first_created is True
    assert second_created is False


def test_winner_is_deterministic_and_order_independent(tmp_path):
    store = LotteryStore(str(tmp_path / "lottery.db"))
    tickets = []
    for index in range(3):
        ticket, _ = store.add_ticket(
            period_end=2_000_000_000,
            payer=f"0x{index + 1:040x}",
            payment_tx=f"0x{index + 10:064x}",
            amount=50_000,
            created_at=1_999_999_000 + index,
        )
        tickets.append(ticket)
    selected_a = select_winner(
        tickets,
        period_end=2_000_000_000,
        block_hash="0x" + "cd" * 32,
    )
    selected_b = select_winner(
        list(reversed(tickets)),
        period_end=2_000_000_000,
        block_hash="0x" + "cd" * 32,
    )
    assert selected_a == selected_b
