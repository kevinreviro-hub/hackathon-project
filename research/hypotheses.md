# RS21/RS55/RSI Crossover Strategy — Research Log

## Definitions used (no access to internal `ratio_charts_data`/`stockedge_technical_indicators` tables — reconstructed from raw OHLC via Gurufocus NSE data, 2019-01-01 to 2024-12-31)

- Universe: RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, SBIN, HINDUNILVR, ITC, BHARTIARTL, KOTAKBANK, LT, AXISBANK, MARUTI, SUNPHARMA, TATAMOTORS (15 liquid Nifty50 names, sector-diverse) vs NIFTY50 index.
- `ratio_t = stock_close_t / index_close_t`
- `RS_n,t = (ratio_t / SMA(ratio, n)_t - 1) * 100`  (Mansfield-style relative-strength oscillator; oscillates around 0, matches user's "RS<0 means underperforming" framing)
- `RS21 = RS_21`, `RS55 = RS_55`
- `RSI14` = Wilder's 14-period RSI on stock close price (not on the ratio)
- Costs assumed: 15 bps one-way (slippage + brokerage + STT for cash equity), unless noted.

## User's raw observations → initial hypotheses

**H1 (long-the-turn):** Stock has been underperforming Nifty (RS55<0 and RS21<0) for a while, then RS21 crosses above RS55 (momentum turning up relative to index) → long entry. Better if RSI<50 at the crossover (room to run before overbought).

**H2 (short-the-turn, symmetric):** RS21 crosses below RS55 while RSI<50 → short entry.

**H3 (pullback-continuation):** RS21>RS55 already (relative uptrend intact) but RSI>50 (no fresh discount) → wait for RSI to dip <50 and then cross back above 50 → buy on that RSI re-cross, riding the existing RS uptrend at a better price.

## Quant-research checklist before trusting any of this (first principles)

1. **Event study before strategy.** Before building entries/exits/stops, measure forward returns (5/10/21/42/63d) conditioned on the signal vs. unconditional/randomized baseline, per stock and pooled. If there's no edge here, no amount of stop-loss engineering will save it.
2. **Lookahead bias.** SMA(ratio,55) needs 55 days of history before it's valid; RSI needs 14. Signals before day ~60 are excluded.
3. **Survivorship / look-ahead in universe choice.** All 15 names survived and were liquid Nifty50 members throughout 2019-24 — this is a real bias (we picked "stocks we know"), flagged for the team; production version needs point-in-time Nifty500 membership, not hand-picked blue chips.
4. **Multiple testing.** 15 stocks × ~1500 days → many candidate crossovers. Need to check signal counts are large enough for statistical significance, and that "RSI<50 helps" isn't just curve-fit noise (split sample / walk-forward).
5. **Regime dependence.** 2019-24 contains: 2020 COVID crash+V-recovery, 2021 melt-up, 2022 bear (rate hikes), 2023-24 bull. A mean-reversion-vs-index signal should be tested per regime, not just pooled, since pooled win rate can hide regime concentration.
6. **Long vs short asymmetry.** Indian cash equity shorting is synthetic (futures/options) with margin and time-decay costs; a short signal needs a derivatives P&L model, not just spot returns. This matters directly for H2 and for the "satellite strategy on pledged capital" ask.
7. **Capital efficiency.** If signals are rare per stock (a stock chops sideways for years before underperforming and turning), the long-only book sits in cash a lot → low portfolio CAGR despite good per-trade IRR. This is exactly the dynamic the user flagged. Plan: measure per-trade IRR vs capital-employed-weighted CAGR separately, then design a satellite (margin-funded, higher turnover, basket-diversified) overlay if idle capital is confirmed to be the binding constraint, not signal quality.

## Status

- [ ] Run H1 event study (long-the-turn, RSI filter)
- [ ] Run H2 event study (short-the-turn)
- [ ] Run H3 event study (pullback continuation)
- [ ] Regime split
- [ ] Build position-managed backtest (entries/exits/sizing/stops) for the best-surviving hypothesis
- [ ] Portfolio-level CAGR/Sharpe/MaxDD with capital idle-time accounting
- [ ] Satellite strategy design if idle capital confirmed as binding constraint
