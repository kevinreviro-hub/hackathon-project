"""Offline tests for the scanner and gap-strategy backtest (no network)."""

import pandas as pd

from premarket.backtest import build_daily_study, gap_strategy
from premarket.scanner import scan_premarket


class FakeClient:
    """Returns a fixed intraday payload regardless of args."""

    def __init__(self, payload):
        self._payload = payload

    def intraday(self, *args, **kwargs):
        return self._payload


# Two trading days at 5min bars. Day 1 sets the prior close; day 2 gaps up in
# pre-market and then rises during the regular session.
PAYLOAD = {
    "Meta Data": {"6. Time Zone": "US/Eastern"},
    "Time Series (5min)": {
        # Day 1 regular session -> prev_close = 100
        "2026-06-16 09:30:00": {"1. open": "100", "2. high": "100", "3. low": "100", "4. close": "100", "5. volume": "500"},
        "2026-06-16 15:55:00": {"1. open": "100", "2. high": "100", "3. low": "100", "4. close": "100", "5. volume": "500"},
        # Day 2 pre-market -> last PM close 105 => gap +5%
        "2026-06-17 04:00:00": {"1. open": "104", "2. high": "104", "3. low": "104", "4. close": "104", "5. volume": "200"},
        "2026-06-17 09:25:00": {"1. open": "105", "2. high": "105", "3. low": "105", "4. close": "105", "5. volume": "300"},
        # Day 2 regular session: open 105 -> close 108 => +2.857% intraday
        "2026-06-17 09:30:00": {"1. open": "105", "2. high": "106", "3. low": "105", "4. close": "106", "5. volume": "900"},
        "2026-06-17 15:55:00": {"1. open": "107", "2. high": "108", "3. low": "107", "4. close": "108", "5. volume": "900"},
    },
}


def test_build_daily_study():
    study = build_daily_study("TEST", months=["2026-06"], interval="5min", client=FakeClient(PAYLOAD))
    # Day 1 has no prior close -> dropped; only day 2 yields a row.
    assert len(study) == 1
    row = study.iloc[0]
    assert row["prev_close"] == 100.0
    assert round(row["gap_pct"], 2) == 5.0
    assert row["regular_open"] == 105.0
    assert row["regular_close"] == 108.0
    assert round(row["day_ret_pct"], 3) == 2.857


def test_gap_strategy_momentum_long_win():
    study = build_daily_study("TEST", months=["2026-06"], interval="5min", client=FakeClient(PAYLOAD))
    res = gap_strategy(study, gap_threshold=2.0)
    assert res["trades"] == 1
    assert res["gap_up_days"] == 1
    assert res["win_rate_pct"] == 100.0
    assert round(res["avg_ret_pct"], 3) == 2.857


def test_gap_strategy_fade_is_inverse_of_momentum():
    study = build_daily_study("TEST", months=["2026-06"], interval="5min", client=FakeClient(PAYLOAD))
    mom = gap_strategy(study, gap_threshold=2.0, mode="momentum")
    fade = gap_strategy(study, gap_threshold=2.0, mode="fade")
    # same single gap-up day, opposite sign, no costs
    assert round(mom["total_ret_pct"] + fade["total_ret_pct"], 6) == 0.0
    assert fade["win_rate_pct"] == 0.0


def test_gap_strategy_costs_reduce_return():
    study = build_daily_study("TEST", months=["2026-06"], interval="5min", client=FakeClient(PAYLOAD))
    gross = gap_strategy(study, gap_threshold=2.0)
    net = gap_strategy(study, gap_threshold=2.0, fees_bps=5, slippage_bps=5)
    # round trip cost = 2 * (5+5) bps = 0.20%
    assert round(net["cost_per_trade_pct"], 4) == 0.20
    assert round(gross["total_ret_pct"] - net["total_ret_pct"], 4) == 0.20


def test_gap_strategy_threshold_filters_out():
    study = build_daily_study("TEST", months=["2026-06"], interval="5min", client=FakeClient(PAYLOAD))
    assert gap_strategy(study, gap_threshold=10.0)["trades"] == 0


def test_scanner_ranks_by_gap_times_volume():
    df = scan_premarket(["TEST"], interval="5min", client=FakeClient(PAYLOAD))
    assert list(df["symbol"]) == ["TEST"]
    row = df.iloc[0]
    assert round(row["gap_pct"], 2) == 5.0
    assert row["premarket_volume"] == 500.0          # 200 + 300
    assert round(row["score"], 1) == 2500.0          # 5% * 500
