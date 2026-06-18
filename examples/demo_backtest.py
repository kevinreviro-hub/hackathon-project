"""End-to-end backtest demo on SYNTHETIC data.

The live Alpha Vantage host is blocked by this environment's network egress, so
this script generates a realistic intraday series (with a deliberate gap->trend
edge baked in) and runs it through the REAL backtest code path via a fake client.
Run on your own machine against the live API by dropping the FakeClient and using
`build_daily_study(symbol, start=..., end=...)` instead.
"""

from __future__ import annotations

import random
import sys
from datetime import date, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from premarket.backtest import build_daily_study, gap_strategy
from premarket.scanner import scan_premarket


def _synth_payload(n_days: int = 60, seed: int = 7) -> dict:
    """Build a 5min intraday payload across n_days with a gap->trend tendency:
    bigger pre-market gaps tend to continue during the regular session (+noise)."""
    rng = random.Random(seed)
    series: dict[str, dict] = {}
    day = date(2026, 1, 5)  # a Monday
    prev_close = 100.0
    made = 0
    while made < n_days:
        if day.weekday() < 5:  # skip weekends
            gap = rng.gauss(0, 2.5)                      # pre-market gap in %
            pm_close = prev_close * (1 + gap / 100)
            reg_open = pm_close * (1 + rng.gauss(0, 0.2) / 100)
            # edge: regular session continues ~40% of the gap, plus noise
            drift = 0.40 * gap + rng.gauss(0, 1.5)
            reg_close = reg_open * (1 + drift / 100)

            def put(d: date, t: time, price: float, vol: int):
                series[f"{d} {t.strftime('%H:%M:%S')}"] = {
                    "1. open": f"{price:.2f}", "2. high": f"{price:.2f}",
                    "3. low": f"{price:.2f}", "4. close": f"{price:.2f}",
                    "5. volume": str(vol),
                }

            put(day, time(4, 0), prev_close * (1 + gap / 200), rng.randint(100, 400))
            put(day, time(9, 25), pm_close, rng.randint(200, 800))     # last PM bar
            put(day, time(9, 30), reg_open, rng.randint(800, 2000))    # regular open
            put(day, time(15, 55), reg_close, rng.randint(800, 2000))  # regular close
            prev_close = reg_close
            made += 1
        day += timedelta(days=1)
    return {"Meta Data": {"6. Time Zone": "US/Eastern"}, "Time Series (5min)": series}


class FakeClient:
    def __init__(self, payload):
        self._payload = payload

    def intraday(self, *args, **kwargs):
        return self._payload


def main() -> None:
    client = FakeClient(_synth_payload())
    study = build_daily_study("DEMO", months=["2026-01"], interval="5min", client=client)

    print(f"Daily study: {len(study)} trading days\n")
    print(study.head(8).to_string(index=False))

    print("\n--- momentum vs fade @ |gap|>=2%, 5bps fees + 5bps slippage/side ---")
    for mode in ("momentum", "fade"):
        r = gap_strategy(study, gap_threshold=2.0, mode=mode, fees_bps=5, slippage_bps=5)
        print(f"{mode:>8}  trades={r['trades']:>3}  win%={r['win_rate_pct']:>6}"
              f"  net_avg%={r['avg_ret_pct']:>7}  net_total%={r['total_ret_pct']:>8}"
              f"  gross_total%={r['gross_total_ret_pct']:>8}  compounded%={r['compounded_ret_pct']:>8}")

    print("\n--- momentum across thresholds (gross, no costs) ---")
    for thr in (1.0, 2.0, 3.0):
        r = gap_strategy(study, gap_threshold=thr)
        print(f"|gap|>={thr}%  trades={r['trades']:>3}  win%={r['win_rate_pct']:>6}"
              f"  avg%={r['avg_ret_pct']:>7}  total%={r['total_ret_pct']:>8}")

    print("\n--- scan_premarket (same synthetic feed) ---")
    print(scan_premarket(["DEMO"], interval="5min", client=client).to_string(index=False))


if __name__ == "__main__":
    main()
