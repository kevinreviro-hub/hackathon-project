# Pre-market data extractor

Pulls **US equity pre-market bars (04:00–09:30 ET)** for quant trading, both as
**historical backfill** and as a **live poller**, from
[Alpha Vantage](https://www.alphavantage.co/).

## Why Alpha Vantage (and not TradingView)

TradingView has no public market-data API and blocks automated requests (HTTP
403), so it can't be used as a data source. Alpha Vantage's
`TIME_SERIES_INTRADAY` endpoint supports `extended_hours=true`, which returns the
pre-/post-market bars TradingView won't give you programmatically.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then paste a free key from
                              # https://www.alphavantage.co/support/#api-key
```

> **Free-tier limits:** 25 requests/day, 5/minute. The client throttles to ~12s
> between calls automatically. Each historical *month* of intraday data = 1
> request, so a 6-month backfill of one symbol ≈ 6 requests. Upgrade for heavy use.

## Historical backfill

```bash
# date range (resolved to whole months under the hood)
python -m premarket.cli history AAPL --start 2026-05-01 --end 2026-06-17 -o data/aapl_pm.csv

# explicit months, 5-minute bars, parquet out
python -m premarket.cli history TSLA --months 2026-05 2026-06 --interval 5min -o data/tsla_pm.parquet
```

Output columns: `symbol, timestamp (ET), open, high, low, close, volume` — only
rows inside the pre-market window are kept.

```python
from datetime import date
from premarket import fetch_premarket_history

df = fetch_premarket_history("NVDA", start=date(2026, 5, 1), end=date(2026, 6, 17))
```

## Live monitoring

Polls each symbol during 04:00–09:30 ET and prints the latest pre-market bar plus
a **gap % vs the prior regular-session close** and cumulative pre-market volume —
the inputs most pre-market quant signals key off. Outside the window it idles.

```bash
python -m premarket.cli live AAPL TSLA NVDA --poll 60
```

Programmatic use with your own signal callback:

```python
from premarket import monitor_premarket, LiveQuote

def on_quote(q: LiveQuote):
    if q.gap_pct is not None and abs(q.gap_pct) > 3:
        print(f"GAP ALERT {q.symbol} {q.gap_pct:+.2f}% @ {q.price}")

monitor_premarket(["AAPL", "TSLA"], poll_seconds=60, on_quote=on_quote)
```

## Tests

```bash
python -m pytest tests/ -q
```

Tests run fully offline (synthetic payloads) — no API key or network needed.

## Layout

```
premarket/
  config.py      session constants (04:00–09:30 ET), settings from env
  client.py      Alpha Vantage HTTP client, rate-limit aware
  historical.py  fetch_premarket_history() -> DataFrame / CSV / Parquet
  live.py        monitor_premarket() live poller + gap signal
  cli.py         `python -m premarket.cli history|live`
tests/
  test_premarket.py
```
