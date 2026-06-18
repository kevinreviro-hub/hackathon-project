"""Thin Alpha Vantage HTTP client with rate-limit awareness.

Alpha Vantage signals problems in-band (HTTP 200 with a JSON key):
  - "Error Message" : bad params / unknown symbol
  - "Note"          : per-minute rate limit hit (free tier: 5 req/min)
  - "Information"    : daily cap hit (free tier: 25 req/day) or premium-only endpoint
We surface all three as AlphaVantageError so callers fail loudly.
"""

from __future__ import annotations

import time as _time
from typing import Any

import requests

from .config import Settings


class AlphaVantageError(RuntimeError):
    """Raised for any API-level error returned by Alpha Vantage."""


class AlphaVantageClient:
    def __init__(self, settings: Settings | None = None, *, min_interval_s: float = 12.0):
        # Free tier allows 5 requests/minute -> ~12s spacing keeps us under it.
        self.settings = settings or Settings.from_env()
        self.min_interval_s = min_interval_s
        self._last_call = 0.0
        self._session = requests.Session()

    def _throttle(self) -> None:
        elapsed = _time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            _time.sleep(self.min_interval_s - elapsed)

    def get(self, **params: Any) -> dict[str, Any]:
        """Issue a single query, returning parsed JSON or raising on API errors."""
        self._throttle()
        params["apikey"] = self.settings.api_key
        resp = self._session.get(self.settings.base_url, params=params, timeout=30)
        self._last_call = _time.monotonic()
        resp.raise_for_status()
        data = resp.json()

        if "Error Message" in data:
            raise AlphaVantageError(data["Error Message"])
        if "Note" in data:
            raise AlphaVantageError(f"Rate limit: {data['Note']}")
        if "Information" in data:
            raise AlphaVantageError(f"API limit / premium: {data['Information']}")
        return data

    def intraday(
        self,
        symbol: str,
        *,
        interval: str = "1min",
        month: str | None = None,
        outputsize: str = "full",
        extended_hours: bool = True,
    ) -> dict[str, Any]:
        """TIME_SERIES_INTRADAY. `month` (YYYY-MM) pulls a specific historical month."""
        params: dict[str, Any] = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "extended_hours": "true" if extended_hours else "false",
        }
        if month:
            params["month"] = month
        return self.get(**params)
