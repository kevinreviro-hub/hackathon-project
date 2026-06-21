import pandas as pd
import numpy as np
import glob
import os

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

def load(symbol):
    df = pd.read_csv(os.path.join(RAW_DIR, f"{symbol}.csv"), parse_dates=["date"])
    return df.sort_values("date").drop_duplicates("date").set_index("date")

def wilder_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    rsi[avg_loss == 0] = 100
    return rsi

def build_indicators(symbol, index_df):
    stock = load(symbol)
    df = stock[["close"]].join(index_df[["close"]], lsuffix="_stock", rsuffix="_index", how="inner")
    df["ratio"] = df["close_stock"] / df["close_index"]
    for n in (21, 55):
        sma = df["ratio"].rolling(n).mean()
        df[f"rs{n}"] = (df["ratio"] / sma - 1) * 100
    df["rsi14"] = wilder_rsi(df["close_stock"], 14)
    df["symbol"] = symbol
    # forward returns on stock close
    for h in (5, 10, 21, 42, 63):
        df[f"fwd_{h}"] = df["close_stock"].shift(-h) / df["close_stock"] - 1
    return df.dropna(subset=["rs55"])  # require warm-up

def get_universe():
    files = glob.glob(os.path.join(RAW_DIR, "*.csv"))
    syms = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return sorted(s for s in syms if s != "NIFTY50")

if __name__ == "__main__":
    idx = load("NIFTY50")
    out = []
    for s in get_universe():
        out.append(build_indicators(s, idx))
    panel = pd.concat(out)
    panel.to_parquet(os.path.join(os.path.dirname(__file__), "..", "data", "panel.parquet"))
    print(panel.shape, panel["symbol"].nunique())
    print(panel.groupby("symbol").size())
