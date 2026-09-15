"""Run the one-shot draw check periodically without automatic payout retries."""

from __future__ import annotations

import asyncio
import json

from app.draw import run_draw


async def main() -> None:
    while True:
        try:
            print(json.dumps(await run_draw()), flush=True)
        except Exception as exc:
            print(json.dumps({"action": "error", "error": str(exc)}), flush=True)
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
