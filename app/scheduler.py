"""Run the one-shot draw check periodically without automatic payout retries."""

from __future__ import annotations

import asyncio
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import settings
from app.draw import run_draw


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
    while True:
        try:
            result = await run_draw()
            logger.info("draw check %s", json.dumps(result, sort_keys=True))
        except Exception as exc:
            logger.exception("draw check failed error=%s", exc)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
