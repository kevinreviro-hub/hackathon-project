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


def gap_strategy(
    study: pd.DataFrame,
    *,
    gap_threshold: float = 2.0,
    mode: str = "momentum",
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
    capital_fraction: float = 1.0,
) -> dict:
    """Backtest the open->close move on days where |gap| >= threshold.

    mode:
      "momentum" - long gap-up, short gap-down (bet the gap continues)
      "fade"     - short gap-up, long gap-down (bet the gap reverts)

    Costs: `fees_bps` + `slippage_bps` are charged per side, so a round trip
    deducts 2 x (fees_bps + slippage_bps) basis points from each trade's return
    (1 bp = 0.01%). `capital_fraction` (0-1) is the share of the book put on per
    trade, used only for the compounded equity figure.

    Per-trade returns are un-compounded percentage points; `compounded_ret_pct`
    sequences them through equity at the given capital fraction.
    """
    if mode not in ("momentum", "fade"):
        raise ValueError("mode must be 'momentum' or 'fade'")
    if study.empty:
        return {"trades": 0, "mode": mode}

    longs_up = study[study["gap_pct"] >= gap_threshold].copy()
    shorts_dn = study[study["gap_pct"] <= -gap_threshold].copy()
    sign = 1.0 if mode == "momentum" else -1.0

    longs_up["trade_ret"] = sign * longs_up["day_ret_pct"]    # gap-up day
    shorts_dn["trade_ret"] = -sign * shorts_dn["day_ret_pct"] # gap-down day
    trades = pd.concat([longs_up, shorts_dn], ignore_index=True)
    if trades.empty:
        return {"trades": 0, "mode": mode, "gap_threshold": gap_threshold}

    cost_pct = 2.0 * (fees_bps + slippage_bps) / 100.0        # bps -> pct, round trip
    trades["gross_ret"] = trades["trade_ret"]
    trades["net_ret"] = trades["trade_ret"] - cost_pct
    trades = trades.sort_values("date")

    equity = 1.0
    for r in trades["net_ret"]:
        equity *= (1.0 + capital_fraction * r / 100.0)

    wins = (trades["net_ret"] > 0).sum()
    return {
        "trades": int(len(trades)),
        "mode": mode,
        "gap_threshold": gap_threshold,
        "fees_bps": fees_bps,
        "slippage_bps": slippage_bps,
        "cost_per_trade_pct": round(cost_pct, 4),
        "gap_up_days": int(len(longs_up)),
        "gap_down_days": int(len(shorts_dn)),
        "win_rate_pct": round(wins / len(trades) * 100.0, 2),
        "avg_ret_pct": round(float(trades["net_ret"].mean()), 4),
        "total_ret_pct": round(float(trades["net_ret"].sum()), 4),
        "gross_total_ret_pct": round(float(trades["gross_ret"].sum()), 4),
        "compounded_ret_pct": round((equity - 1.0) * 100.0, 4),
        "best_pct": round(float(trades["net_ret"].max()), 4),
        "worst_pct": round(float(trades["net_ret"].min()), 4),
    }
