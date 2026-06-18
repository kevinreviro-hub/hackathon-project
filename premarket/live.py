"""Live pre-market monitoring.

Polls the latest intraday bars during the pre-market window and emits the most
recent bar per symbol, along with a gap-vs-previous-close signal that quant
strategies commonly key off. Outside 04:00-09:30 ET it idles instead of burning
API calls.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Sequence

import pandas as pd

from .client import AlphaVantageClient
from .config import ET, PREMARKET_CLOSE, PREMARKET_OPEN, in_premarket
from .historical import _parse_intraday


@dataclass
class LiveQuote:
    symbol: str
    timestamp: datetime          # latest pre-market bar time (ET)
    price: float                 # latest pre-market close
    prev_close: float | None     # prior regular-session close
    premarket_volume: float      # cumulative pre-market volume so far today
    gap_pct: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.prev_close:
            self.gap_pct = (self.price - self.prev_close) / self.prev_close * 100.0


def _prev_close(payload: dict, interval: str) -> float | None:
    """Last regular-session (>=09:30) close on the most recent prior day."""
    df = _parse_intraday(payload, interval)
    if df.empty:
        return None
    reg = df[df["timestamp"].dt.time >= PREMARKET_CLOSE]
    if reg.empty:
        return None
    latest_day = df["timestamp"].dt.date.max()
    prior = reg[reg["timestamp"].dt.date < latest_day]
    if prior.empty:
        return None
    return float(prior.sort_values("timestamp").iloc[-1]["close"])


def _latest_premarket(payload: dict, interval: str) -> tuple[pd.Timestamp, float, float] | None:
    df = _parse_intraday(payload, interval)
    if df.empty:
        return None
    today = df["timestamp"].dt.date.max()
    t = df["timestamp"].dt.time
    pm = df[(df["timestamp"].dt.date == today) & (t >= PREMARKET_OPEN) & (t < PREMARKET_CLOSE)]
    if pm.empty:
        return None
    pm = pm.sort_values("timestamp")
    last = pm.iloc[-1]
    return last["timestamp"], float(last["close"]), float(pm["volume"].sum())


def poll_once(symbol: str, client: AlphaVantageClient, *, interval: str = "1min") -> LiveQuote | None:
    """Single snapshot of the latest pre-market bar for `symbol`, or None if no PM data."""
    payload = client.intraday(symbol, interval=interval, outputsize="full", extended_hours=True)
    latest = _latest_premarket(payload, interval)
    if latest is None:
        return None
    ts, price, pm_vol = latest
    return LiveQuote(
        symbol=symbol,
        timestamp=ts.to_pydatetime(),
        price=price,
        prev_close=_prev_close(payload, interval),
        premarket_volume=pm_vol,
    )


def monitor_premarket(
    symbols: Sequence[str],
    *,
    interval: str = "1min",
    poll_seconds: float = 60.0,
    on_quote: Callable[[LiveQuote], None] | None = None,
    client: AlphaVantageClient | None = None,
    respect_session: bool = True,
    max_polls: int | None = None,
) -> None:
    """Poll `symbols` every `poll_seconds` during the pre-market window.

    `on_quote` is invoked for each fresh quote (defaults to printing). Set
    `respect_session=False` to poll regardless of the clock (useful for testing).
    `max_polls` bounds the loop for one-shot/test runs.
    """
    client = client or AlphaVantageClient()
    on_quote = on_quote or _default_sink
    polls = 0

    while max_polls is None or polls < max_polls:
        now_et = datetime.now(ET)
        if respect_session and not in_premarket(now_et.time()):
            _time.sleep(poll_seconds)
            continue
        for symbol in symbols:
            try:
                quote = poll_once(symbol, client, interval=interval)
            except Exception as exc:  # keep the loop alive on transient API errors
                print(f"[{symbol}] poll error: {exc}")
                continue
            if quote is not None:
                on_quote(quote)
        polls += 1
        _time.sleep(poll_seconds)


def _default_sink(q: LiveQuote) -> None:
    gap = f"{q.gap_pct:+.2f}%" if q.gap_pct is not None else "n/a"
    print(
        f"{q.timestamp:%Y-%m-%d %H:%M} ET  {q.symbol:<6} "
        f"px={q.price:<10.4f} gap={gap:<8} pm_vol={q.premarket_volume:,.0f}"
    )
