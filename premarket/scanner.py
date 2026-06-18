"""Pre-market gap scanner.

Ranks a watchlist by a simple conviction score = |gap %| x pre-market volume,
so the names with both a big gap AND real participation float to the top
(a lone gap on 200 shares is noise; a gap on heavy volume is a signal).
"""

from __future__ import annotations

import pandas as pd

from .client import AlphaVantageClient
from .live import poll_once


def scan_premarket(
    symbols,
    *,
    interval: str = "1min",
    client: AlphaVantageClient | None = None,
) -> pd.DataFrame:
    """Snapshot every symbol once and return a ranked gap table.

    Columns: symbol, price, prev_close, gap_pct, premarket_volume, score
    Sorted by score descending. Symbols with no pre-market data are skipped.
    """
    client = client or AlphaVantageClient()
    rows = []
    for symbol in symbols:
        try:
            q = poll_once(symbol, client, interval=interval)
        except Exception as exc:
            print(f"[{symbol}] scan error: {exc}")
            continue
        if q is None or q.gap_pct is None:
            continue
        rows.append(
            {
                "symbol": q.symbol,
                "price": q.price,
                "prev_close": q.prev_close,
                "gap_pct": q.gap_pct,
                "premarket_volume": q.premarket_volume,
                "score": abs(q.gap_pct) * q.premarket_volume,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("score", ascending=False).reset_index(drop=True)
