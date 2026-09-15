"""Environment-backed configuration for the lottery service."""

from __future__ import annotations

import os
from dataclasses import dataclass

CHAIN_ID = 4217
USDC_E = "0x20C000000000000000000000b9537d11c60E8b50"
USDC_DECIMALS = 6
TICKET_PRICE = "0.05"
TICKET_PRICE_BASE_UNITS = 50_000
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass(frozen=True)
class Settings:
    rpc_url: str = os.getenv("TEMPO_RPC_URL", "https://rpc.tempo.xyz")
    payment_destination: str = os.getenv("PAYMENT_DESTINATION", ZERO_ADDRESS)
    payment_currency: str = os.getenv("PAYMENT_CURRENCY", USDC_E)
    database_path: str = os.getenv("LOTTERY_DATABASE_PATH", "data/lottery.db")
    draw_weekday_utc: int = _integer("DRAW_WEEKDAY_UTC", 6, 0, 6)
    draw_hour_utc: int = _integer("DRAW_HOUR_UTC", 20, 0, 23)
    payout_bps: int = _integer("PAYOUT_BPS", 9000, 1, 10_000)
    lottery_enabled: bool = _boolean("LOTTERY_ENABLED")


settings = Settings()
