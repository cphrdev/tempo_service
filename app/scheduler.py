"""Run the one-shot draw check periodically without automatic payout retries."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import settings
from app.draw import retry_latest_failed_payout, run_draw
from app.lottery import previous_period_end


def configure_logging() -> None:
    log_path = Path(settings.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    formatter.converter = __import__("time").gmtime
    file_handler = TimedRotatingFileHandler(log_path, when="midnight", backupCount=30, encoding="utf-8", utc=True)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    last_run_period_end: int | None = None
    while True:
        try:
            now = int(datetime.now(UTC).timestamp())
            period_end = previous_period_end(
                now + 1,
                settings.draw_weekday_utc,
                settings.draw_hour_utc,
                settings.draw_minute_utc,
                settings.draw_second_utc,
            )
            due = 0 <= now - period_end < settings.draw_trigger_window_seconds
            if due and period_end != last_run_period_end:
                retry = await retry_latest_failed_payout()
                result = await run_draw(now=now)
                for outcome in (retry, result):
                    if outcome["action"] in {"paid", "failed"}:
                        logger.info("payout result %s", json.dumps(outcome, sort_keys=True))
                last_run_period_end = period_end
        except Exception as exc:
            logger.exception("scheduled draw failed error=%s", exc)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
