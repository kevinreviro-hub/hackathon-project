"""Shared configuration and US pre-market session constants."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# US market trades on Eastern time; Alpha Vantage returns intraday
# timestamps already expressed in US/Eastern.
ET = ZoneInfo("America/New_York")

# Pre-market session window. Bars are kept when PREMARKET_OPEN <= t < PREMARKET_CLOSE.
PREMARKET_OPEN = time(4, 0)
PREMARKET_CLOSE = time(9, 30)


@dataclass(frozen=True)
class Settings:
    """Runtime settings, sourced from the environment."""

    api_key: str
    base_url: str = "https://www.alphavantage.co/query"

    @classmethod
    def from_env(cls) -> "Settings":
        key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "ALPHAVANTAGE_API_KEY is not set. Copy .env.example to .env and "
                "add a key from https://www.alphavantage.co/support/#api-key"
            )
        return cls(api_key=key)


def in_premarket(t: time) -> bool:
    """True if a (timezone-naive, ET) clock time falls in the pre-market window."""
    return PREMARKET_OPEN <= t < PREMARKET_CLOSE
