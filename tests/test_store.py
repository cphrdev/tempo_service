from app.store import LotteryStore


def test_latest_failed_draw_returns_newest_failure(tmp_path):
    store = LotteryStore(str(tmp_path / "lottery.db"))
    for period_end in (1_000, 2_000):
        store.create_selected_draw(
            period_end=period_end,
            ticket_count=1,
            pool_amount=50_000,
            payout_amount=45_000,
            winner="0x1111111111111111111111111111111111111111",
            winner_ticket_id=None,
            randomness_block=1,
            randomness_hash="0x" + "ab" * 32,
            seed="0x" + "cd" * 32,
        )
        store.mark_failed(period_end, "temporary RPC failure")

    assert store.latest_failed_draw().period_end == 2_000
