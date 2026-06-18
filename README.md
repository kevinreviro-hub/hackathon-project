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

## Gap scanner

Rank a watchlist by **|gap %| × pre-market volume** — surfaces names that are
gapping *and* actually trading (a gap on light volume is noise):

```bash
python -m premarket.cli scan AAPL TSLA NVDA AMD META -o data/scan.csv
```

```
symbol   price  prev_close  gap_pct  premarket_volume      score
  NVDA  130.50      125.00     4.40            850000  3740000.0
   AMD   98.20       96.00     2.29            300000   687000.0
  ...
```

## Gap backtest

Tests whether the pre-market gap predicts the regular session: on `|gap| ≥`
threshold, go **long on a gap-up / short on a gap-down at the open, exit at the
close**. Uses the same feed (PM + regular bars come together).

```bash
# momentum (default), with realistic costs
python -m premarket.cli backtest TSLA --start 2026-01-01 --end 2026-06-17 \
    --gap 2 --fees-bps 1 --slippage-bps 5 -o data/tsla_study.csv

# fade variant: bet the gap reverts
python -m premarket.cli backtest TSLA --start 2026-01-01 --end 2026-06-17 --gap 2 --mode fade
```

```
Pre-market gap strategy on TSLA (mode=momentum, |gap| >= 2.0%):
  trades: 41
  win_rate_pct: 58.54
  cost_per_trade_pct: 0.12        # round trip = 2 x (fees + slippage) bps
  avg_ret_pct: 0.31               # net of costs
  total_ret_pct: 12.71
  gross_total_ret_pct: 17.63
  compounded_ret_pct: 13.40       # sequenced through equity
  ...
```

Flags: `--mode {momentum,fade}`, `--fees-bps`, `--slippage-bps` (both per side),
`--capital-fraction` (share of book per trade, for the compounded figure).

```python
from datetime import date
from premarket import build_daily_study, gap_strategy

study = build_daily_study("TSLA", start=date(2026, 1, 1), end=date(2026, 6, 17))
print(gap_strategy(study, gap_threshold=2.0))
```

> Returns are simple, un-compounded percentage points (max one trade/day), no
> fees/slippage — it's a signal sniff-test, not a production backtest.

### Try it without an API key

`examples/demo_backtest.py` runs the full backtest path on a synthetic feed (with
a gap→trend edge baked in), so you can see the pipeline work before wiring a key:

```bash
python examples/demo_backtest.py
```

> Note: some sandboxed environments block outbound access to
> `www.alphavantage.co`. If you hit `Host not in allowlist`, add the host to your
> egress settings or run locally — then swap the demo's fake client for
> `build_daily_study(symbol, start=..., end=...)`.

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
  scanner.py     scan_premarket() watchlist ranking by gap x volume
  backtest.py    build_daily_study() + gap_strategy() gap backtest
  cli.py         `python -m premarket.cli history|live|scan|backtest`
tests/
  test_premarket.py   session-window math
  test_strategy.py    scanner + backtest
```
