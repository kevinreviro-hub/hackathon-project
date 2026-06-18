"""Command-line entrypoint for pre-market extraction.

Examples
--------
Historical backfill to CSV:
    python -m premarket.cli history AAPL --start 2026-05-01 --end 2026-06-17 -o data/aapl_pm.csv

Live monitoring during the pre-market window:
    python -m premarket.cli live AAPL TSLA NVDA --poll 60
"""

from __future__ import annotations

import argparse
from datetime import date

from .backtest import build_daily_study, gap_strategy
from .historical import fetch_premarket_history
from .live import monitor_premarket
from .scanner import scan_premarket


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _cmd_history(args: argparse.Namespace) -> int:
    df = fetch_premarket_history(
        args.symbol,
        start=args.start,
        end=args.end,
        months=args.months,
        interval=args.interval,
    )
    if df.empty:
        print("No pre-market bars found for that range.")
        return 1

    print(df.head(10).to_string(index=False))
    print(f"... {len(df):,} pre-market bars "
          f"({df['timestamp'].min()} -> {df['timestamp'].max()} ET)")

    if args.out:
        if args.out.endswith(".parquet"):
            df.to_parquet(args.out, index=False)
        else:
            df.to_csv(args.out, index=False)
        print(f"wrote {args.out}")
    return 0


def _cmd_live(args: argparse.Namespace) -> int:
    monitor_premarket(
        args.symbols,
        interval=args.interval,
        poll_seconds=args.poll,
        respect_session=not args.ignore_session,
        max_polls=args.max_polls,
    )
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    df = scan_premarket(args.symbols, interval=args.interval)
    if df.empty:
        print("No pre-market data for any of those symbols right now.")
        return 1
    print(df.to_string(index=False))
    if args.out:
        df.to_csv(args.out, index=False)
        print(f"wrote {args.out}")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    study = build_daily_study(
        args.symbol, start=args.start, end=args.end, months=args.months, interval=args.interval
    )
    if study.empty:
        print("No usable trading days in that range.")
        return 1
    result = gap_strategy(study, gap_threshold=args.gap)
    print(f"Pre-market gap strategy on {args.symbol} (|gap| >= {args.gap}%):")
    for k, v in result.items():
        print(f"  {k}: {v}")
    if args.out:
        study.to_csv(args.out, index=False)
        print(f"wrote daily study -> {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="premarket", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    h = sub.add_parser("history", help="Backfill historical pre-market bars")
    h.add_argument("symbol")
    h.add_argument("--start", type=_parse_date, help="YYYY-MM-DD")
    h.add_argument("--end", type=_parse_date, help="YYYY-MM-DD")
    h.add_argument("--months", nargs="*", help="explicit months e.g. 2026-05 2026-06")
    h.add_argument("--interval", default="1min", choices=["1min", "5min", "15min", "30min", "60min"])
    h.add_argument("-o", "--out", help="output path (.csv or .parquet)")
    h.set_defaults(func=_cmd_history)

    l = sub.add_parser("live", help="Poll live pre-market quotes")
    l.add_argument("symbols", nargs="+")
    l.add_argument("--interval", default="1min", choices=["1min", "5min", "15min", "30min", "60min"])
    l.add_argument("--poll", type=float, default=60.0, help="seconds between polls")
    l.add_argument("--ignore-session", action="store_true", help="poll even outside 04:00-09:30 ET")
    l.add_argument("--max-polls", type=int, default=None, help="stop after N poll cycles")
    l.set_defaults(func=_cmd_live)

    s = sub.add_parser("scan", help="Rank a watchlist by pre-market gap x volume")
    s.add_argument("symbols", nargs="+")
    s.add_argument("--interval", default="1min", choices=["1min", "5min", "15min", "30min", "60min"])
    s.add_argument("-o", "--out", help="output CSV path")
    s.set_defaults(func=_cmd_scan)

    b = sub.add_parser("backtest", help="Backtest the pre-market gap -> regular session move")
    b.add_argument("symbol")
    b.add_argument("--start", type=_parse_date, help="YYYY-MM-DD")
    b.add_argument("--end", type=_parse_date, help="YYYY-MM-DD")
    b.add_argument("--months", nargs="*", help="explicit months e.g. 2026-05 2026-06")
    b.add_argument("--interval", default="5min", choices=["1min", "5min", "15min", "30min", "60min"])
    b.add_argument("--gap", type=float, default=2.0, help="|gap %%| threshold to trade")
    b.add_argument("-o", "--out", help="write the per-day study to CSV")
    b.set_defaults(func=_cmd_backtest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
