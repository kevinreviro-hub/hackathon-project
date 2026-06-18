"""Offline tests for the session-filtering logic (no network / no API key)."""

import pandas as pd

from premarket.historical import _filter_premarket, _parse_intraday, _months_between
from premarket.live import _latest_premarket, _prev_close
from datetime import date


# A synthetic Alpha Vantage payload spanning prior-day regular session + today's
# pre-market, so we can assert the window math without calling the API.
PAYLOAD = {
    "Meta Data": {"6. Time Zone": "US/Eastern"},
    "Time Series (1min)": {
        # prior trading day, regular session close
        "2026-06-16 15:59:00": {"1. open": "200", "2. high": "201", "3. low": "199", "4. close": "200.00", "5. volume": "1000"},
        # today's pre-market bars (04:00-09:29)
        "2026-06-17 03:59:00": {"1. open": "201", "2. high": "201", "3. low": "201", "4. close": "201.00", "5. volume": "10"},  # before 04:00 -> excluded
        "2026-06-17 04:00:00": {"1. open": "202", "2. high": "202", "3. low": "202", "4. close": "202.00", "5. volume": "50"},
        "2026-06-17 08:30:00": {"1. open": "205", "2. high": "206", "3. low": "204", "4. close": "206.00", "5. volume": "300"},
        "2026-06-17 09:30:00": {"1. open": "207", "2. high": "207", "3. low": "207", "4. close": "207.00", "5. volume": "999"},  # regular open -> excluded
    },
}


def test_parse_and_filter_window():
    df = _filter_premarket(_parse_intraday(PAYLOAD, "1min"))
    times = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M").tolist()
    # only 04:00 and 08:30 of today survive
    assert times == ["2026-06-17 04:00", "2026-06-17 08:30"]
    assert df["close"].tolist() == [202.0, 206.0]


def test_latest_premarket_and_volume():
    ts, price, vol = _latest_premarket(PAYLOAD, "1min")
    assert price == 206.0          # most recent PM bar
    assert vol == 350.0            # 50 + 300, cumulative PM volume
    assert ts.date() == date(2026, 6, 17)


def test_prev_close_uses_prior_day_regular_session():
    assert _prev_close(PAYLOAD, "1min") == 200.0


def test_months_between():
    assert _months_between(date(2026, 5, 15), date(2026, 7, 2)) == ["2026-05", "2026-06", "2026-07"]


def test_empty_payload_is_safe():
    empty = {"Meta Data": {}}
    assert _parse_intraday(empty, "1min").empty
    assert _latest_premarket(empty, "1min") is None
