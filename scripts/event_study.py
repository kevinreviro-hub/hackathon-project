import pandas as pd
import numpy as np
import os

PANEL = os.path.join(os.path.dirname(__file__), "..", "data", "panel.pkl")
HORIZONS = [5, 10, 21, 42, 63]

def load_panel():
    return pd.read_pickle(PANEL)

def regime_label(date):
    if date < pd.Timestamp("2020-02-20"):
        return "2019_precovid"
    if date < pd.Timestamp("2020-06-01"):
        return "2020_covid_crash"
    if date < pd.Timestamp("2021-10-01"):
        return "2020-21_recovery_meltup"
    if date < pd.Timestamp("2022-12-01"):
        return "2022_bear_ratehikes"
    return "2023-24_bull"

def detect_crossovers(panel):
    df = panel.sort_values(["symbol", "date" if "date" in panel.columns else panel.index.name])
    g = df.groupby("symbol")
    prev_rs21 = g["rs21"].shift(1)
    prev_rs55 = g["rs55"].shift(1)
    df["cross_up"] = (prev_rs21 <= prev_rs55) & (df["rs21"] > df["rs55"])
    df["cross_dn"] = (prev_rs21 >= prev_rs55) & (df["rs21"] < df["rs55"])
    df["was_underperforming"] = (g["rs55"].shift(1) < 0) & (g["rs21"].shift(1) < 0)
    return df

def summarize(events, label, baseline):
    rows = []
    for h in HORIZONS:
        col = f"fwd_{h}"
        e = events[col].dropna()
        b = baseline[col].dropna()
        if len(e) == 0:
            continue
        rows.append({
            "signal": label, "horizon": h, "n": len(e),
            "mean_ret_%": round(e.mean()*100, 2),
            "median_ret_%": round(e.median()*100, 2),
            "win_rate_%": round((e > 0).mean()*100, 1),
            "baseline_mean_%": round(b.mean()*100, 2),
            "baseline_win_%": round((b > 0).mean()*100, 1),
            "excess_mean_%": round((e.mean()-b.mean())*100, 2),
        })
    return pd.DataFrame(rows)

def main():
    panel = load_panel().reset_index()
    panel = detect_crossovers(panel)
    baseline = panel  # unconditional, all days, all stocks

    print("=== Universe / sample size ===")
    print(panel.groupby("symbol").size())
    print()

    # H1: long-the-turn — was underperforming, RS21 crosses above RS55
    h1 = panel[panel["cross_up"] & panel["was_underperforming"]]
    h1_rsi = h1[h1["rsi14"] < 50]
    print("=== H1: long-the-turn (underperform -> RS21 x-up RS55) ===")
    print(summarize(h1, "H1_all", baseline).to_string(index=False))
    print()
    print("=== H1b: + RSI<50 filter ===")
    print(summarize(h1_rsi, "H1_rsi<50", baseline).to_string(index=False))
    print()

    # H2: short-the-turn — RS21 crosses below RS55, RSI<50
    h2 = panel[panel["cross_dn"]]
    h2_rsi = h2[h2["rsi14"] < 50]
    print("=== H2: RS21 x-down RS55 (short candidate) ===")
    print(summarize(h2, "H2_all", baseline).to_string(index=False))
    print()
    print("=== H2b: + RSI<50 ===")
    print(summarize(h2_rsi, "H2_rsi<50", baseline).to_string(index=False))
    print()

    # H3: pullback continuation — RS21>RS55 (uptrend), RSI crosses back above 50 from below
    prev_rsi = panel.groupby("symbol")["rsi14"].shift(1)
    rsi_cross_up50 = (prev_rsi <= 50) & (panel["rsi14"] > 50)
    h3 = panel[(panel["rs21"] > panel["rs55"]) & rsi_cross_up50]
    print("=== H3: RS21>RS55 & RSI crosses back above 50 (pullback continuation buy) ===")
    print(summarize(h3, "H3", baseline).to_string(index=False))
    print()

    # regime breakdown for H1b (the user's favorite filter) and H3
    panel["regime"] = panel["date"].apply(regime_label)
    h1_rsi2 = h1_rsi.copy()
    h1_rsi2["regime"] = h1_rsi2["date"].apply(regime_label)
    print("=== H1b by regime (n, mean 21d fwd ret %, win rate %) ===")
    for r, grp in h1_rsi2.groupby("regime"):
        e = grp["fwd_21"].dropna()
        if len(e):
            print(f"{r:25s} n={len(e):4d}  mean21d={e.mean()*100:6.2f}%  win={  (e>0).mean()*100:5.1f}%")

    h3_2 = h3.copy()
    h3_2["regime"] = h3_2["date"].apply(regime_label)
    print()
    print("=== H3 by regime ===")
    for r, grp in h3_2.groupby("regime"):
        e = grp["fwd_21"].dropna()
        if len(e):
            print(f"{r:25s} n={len(e):4d}  mean21d={e.mean()*100:6.2f}%  win={  (e>0).mean()*100:5.1f}%")

    panel.to_pickle(os.path.join(os.path.dirname(__file__), "..", "data", "panel_with_signals.pkl"))

if __name__ == "__main__":
    main()
