"""Historical pre-market backfill.

Pulls intraday bars (extended hours on) for one or more months and keeps only
the pre-market window (04:00-09:30 ET). Returns a tidy DataFrame and can write
CSV/Parquet for downstream quant research.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

from .client import AlphaVantageClient
from .config import PREMARKET_CLOSE, PREMARKET_OPEN

_TS_KEY_PREFIX = "Time Series ("

_COLUMN_MAP = {
    "1. open": "open",
    "2. high": "high",
    "3. low": "low",
    "4. close": "close",
    "5. volume": "volume",
}


def _parse_intraday(payload: dict, interval: str) -> pd.DataFrame:
    key = f"Time Series ({interval})"
    series = payload.get(key)
    if not series:
        # No data for this slice (e.g. market closed all month) -> empty frame.
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame.from_dict(series, orient="index").rename(columns=_COLUMN_MAP)
    df.index = pd.to_datetime(df.index)  # already US/Eastern wall-clock
    df.index.name = "timestamp"
    df = df.reset_index()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col])
    return df


def _filter_premarket(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    t = df["timestamp"].dt.time
    mask = (t >= PREMARKET_OPEN) & (t < PREMARKET_CLOSE)
    return df.loc[mask].sort_values("timestamp").reset_index(drop=True)


def _months_between(start: date, end: date) -> list[str]:
    months: list[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def fetch_premarket_history(
    symbol: str,
    *,
    months: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    interval: str = "1min",
    client: AlphaVantageClient | None = None,
) -> pd.DataFrame:
    """Backfill pre-market bars for `symbol`.

    Provide either an explicit `months` list (["2026-05", "2026-06"]) or a
    `start`/`end` date range. Returns columns:
        symbol, timestamp (ET), open, high, low, close, volume
    """
    client = client or AlphaVantageClient()

    if months is None:
        if start is None or end is None:
            raise ValueError("Pass either `months=[...]` or both `start` and `end`.")
        months = _months_between(start, end)

    frames: list[pd.DataFrame] = []
    for month in months:
        payload = client.intraday(
            symbol, interval=interval, month=month, outputsize="full", extended_hours=True
        )
        frames.append(_filter_premarket(_parse_intraday(payload, interval)))

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not out.empty:
        out.insert(0, "symbol", symbol)
        out = out.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    return out.reset_index(drop=True)
