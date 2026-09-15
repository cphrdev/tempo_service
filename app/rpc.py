"""Minimal Tempo JSON-RPC helpers."""

from __future__ import annotations

import httpx


class TempoRpc:
    def __init__(self, url: str):
        self.url = url

    async def call(self, method: str, params: list) -> object:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self.url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            response.raise_for_status()
            payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "Tempo RPC error"))
        return payload["result"]

    async def block_at_or_after(self, timestamp: int) -> tuple[int, str]:
        latest_hex = await self.call("eth_blockNumber", [])
        high = int(str(latest_hex), 16)
        latest = await self._block(high)
        if int(latest["timestamp"], 16) < timestamp:
            raise RuntimeError("randomness block has not been produced yet")

        low = 0
        while low < high:
            middle = (low + high) // 2
            block = await self._block(middle)
            if int(block["timestamp"], 16) < timestamp:
                low = middle + 1
            else:
                high = middle
        block = await self._block(low)
        return low, str(block["hash"])

    async def _block(self, number: int) -> dict:
        block = await self.call("eth_getBlockByNumber", [hex(number), False])
        if not isinstance(block, dict) or not block.get("hash"):
            raise RuntimeError(f"block {number} was not returned by Tempo RPC")
        return block
