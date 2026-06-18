"""Quick pre-market gap study + backtest.

Question: does the pre-market gap predict the regular session's open->close move?

build_daily_study() turns intraday bars into one row per trading day:
    date, prev_close, premarket_close, gap_pct, regular_open, regular_close, day_ret_pct
gap_strategy() then backtests a naive rule: when |gap| clears a threshold, take
the regular session (long on gap-up, short on gap-down) and exit at the close.

The same Alpha Vantage intraday feed (extended_hours=true) carries BOTH the
pre-market and regular-session bars, so no second data source is needed.
"""

from __future__ import annotations

from datetime import date, time
from typing import Iterable

import pandas as pd

from .client import AlphaVantageClient
from .config import PREMARKET_CLOSE, PREMARKET_OPEN
from .historical import _months_between, _parse_intraday

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)


def _fetch_full_intraday(
    symbol: str,
    months: Iterable[str],
    interval: str,
    client: AlphaVantageClient,
) -> pd.DataFrame:
    frames = [
        _parse_intraday(
            client.intraday(symbol, interval=interval, month=m, outputsize="full", extended_hours=True),
            interval,
        )
        for m in months
    ]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        return df
    return df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def build_daily_study(
    symbol: str,
    *,
    months: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    interval: str = "5min",
    client: AlphaVantageClient | None = None,
) -> pd.DataFrame:
    """One row per trading day with the pre-market gap and the day's regular return."""
    client = client or AlphaVantageClient()
    if months is None:
        if start is None or end is None:
            raise ValueError("Pass either `months=[...]` or both `start` and `end`.")
        months = _months_between(start, end)

    bars = _fetch_full_intraday(symbol, months, interval, client)
    if bars.empty:
        return pd.DataFrame()

    bars["date"] = bars["timestamp"].dt.date
    bars["clock"] = bars["timestamp"].dt.time

    rows = []
    prev_regular_close: float | None = None
    for day, g in bars.groupby("date", sort=True):
        pm = g[(g["clock"] >= PREMARKET_OPEN) & (g["clock"] < PREMARKET_CLOSE)].sort_values("timestamp")
        reg = g[(g["clock"] >= REGULAR_OPEN) & (g["clock"] < REGULAR_CLOSE)].sort_values("timestamp")

        regular_close = float(reg.iloc[-1]["close"]) if not reg.empty else None
        row = None
        if prev_regular_close is not None and not pm.empty and not reg.empty:
            premarket_close = float(pm.iloc[-1]["close"])
            regular_open = float(reg.iloc[0]["open"])
            row = {
                "date": day,
                "prev_close": prev_regular_close,
                "premarket_close": premarket_close,
                "gap_pct": (premarket_close - prev_regular_close) / prev_regular_close * 100.0,
                "regular_open": regular_open,
                "regular_close": regular_close,
                "day_ret_pct": (regular_close - regular_open) / regular_open * 100.0,
            }
        if row is not None:
            rows.append(row)
        if regular_close is not None:
            prev_regular_close = regular_close

    return pd.DataFrame(rows)


def gap_strategy(study: pd.DataFrame, *, gap_threshold: float = 2.0) -> dict:
    """Backtest: on |gap| >= threshold, take the regular session in the gap's
    direction (long gap-up, short gap-down), exit at close. Returns summary stats.

    Returns are simple, un-compounded percentage points (one trade per day max).
    """
    if study.empty:
        return {"trades": 0}

    longs = study[study["gap_pct"] >= gap_threshold].copy()
    longs["trade_ret"] = longs["day_ret_pct"]               # buy open, sell close
    shorts = study[study["gap_pct"] <= -gap_threshold].copy()
    shorts["trade_ret"] = -shorts["day_ret_pct"]            # short open, cover close

    trades = pd.concat([longs, shorts], ignore_index=True)
    if trades.empty:
        return {"trades": 0, "gap_threshold": gap_threshold}

    wins = (trades["trade_ret"] > 0).sum()
    return {
        "trades": int(len(trades)),
        "gap_threshold": gap_threshold,
        "long_trades": int(len(longs)),
        "short_trades": int(len(shorts)),
        "win_rate_pct": round(wins / len(trades) * 100.0, 2),
        "avg_ret_pct": round(float(trades["trade_ret"].mean()), 4),
        "total_ret_pct": round(float(trades["trade_ret"].sum()), 4),
        "best_pct": round(float(trades["trade_ret"].max()), 4),
        "worst_pct": round(float(trades["trade_ret"].min()), 4),
    }
