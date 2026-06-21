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

- [x] Run H1 event study (long-the-turn, RSI filter)
- [x] Run H2 event study (short-the-turn)
- [x] Run H3 event study (pullback continuation)
- [x] Regime split
- [x] Significance testing with deduplication (avoid pseudo-replication)
- [x] Refinements: market-regime filter, deeper-underperformance threshold
- [ ] Position-managed backtest — **not started, see verdict below**
- [ ] Satellite strategy — **deferred, see verdict below**

## Round 1 results (15 large-cap Nifty50 names, 2019-2024, Mansfield-style RS21/RS55, Wilder RSI14)

**Critical methodology fix:** initial event counts (H1=145, H3=709 "signal-days") were inflated by counting every day a crossover condition held, not independent episodes. A stock that just crossed up stays "post-crossover" for several days, so naive forward-return stats on raw signal-days are pseudo-replicated — they look more significant than they are. After deduplicating to independent episodes (≥15 trading days apart) and running Welch's t-test against the unconditional (all-days, all-stocks) baseline:

| Hypothesis | n (episodes) | 21d excess vs baseline | p-value (21d) | 63d excess | p-value (63d) |
|---|---|---|---|---|---|
| H1 (underperform→RS21 x-up RS55, RSI<50) | 144 | +0.38% | 0.63 | +1.68% | 0.28 |
| H2 (RS21 x-dn RS55, RSI<50 — short) | 36 | **-0.57%** | 0.72 | +1.47% | 0.55 |
| H3 (RS21>RS55, RSI dips & re-crosses 50) | 396 | +0.67% | 0.13 | +0.64% | 0.44 |

**None of these clear the bar for statistical significance (p<0.05) at any horizon, on this universe.** Adding a market-regime filter (Nifty above its own 200-day SMA) or requiring "deep" underperformance (RS55 < -5 before the turn, not just <0) shrinks the sample further (n=23-109) and does not improve p-values — if anything it makes some excess returns turn negative.

**Verdict on the user's specific questions:**
- *"RS21 crosses below RS55 when RSI<50 → short"* — **not supported**. Excess return is negative or indistinguishable from zero at every horizon we tested (n=36, p=0.41-0.77). Blind shorting on this signal in large-cap NSE names would not be expected to make money net of the borrow/derivative-financing cost a real short requires.
- *"RS21>RS55, wait for RSI to dip and cross back above 50"* — this is the largest, cleanest-looking sample (399 independent episodes) and the most promising of the three, but after correcting for pseudo-replication it is **not statistically significant either** (p=0.13 at 21d, the horizon where it looked best).

**Why the null result is plausible, not just "bad luck":** these are 15 of the most liquid, heavily-covered, heavily-arbed large-cap names in India. Their ratio-to-index series has low idiosyncratic dispersion — RS21/RS55 oscillate in a narrow band, so "underperformance" and "crossovers" are mostly noise around a ratio that's anchored close to 1 by index arbitrage and ETF flows. Classic relative-strength reversal effects in the academic and practitioner literature are strongest in **less efficiently-priced names** (mid/small-cap, lower analyst coverage, higher idiosyncratic vol) — exactly where this large-cap-only universe has no power to detect anything.

## Round 2 hypotheses (before committing more capital/research time)

**H4:** The RS21/RS55/RSI crossover effect, if real, lives in **mid/small-cap NSE names**, not large caps, because that's where dispersion vs. the index is large enough for a "turning point" to be economically meaningful rather than noise. Test on a Nifty Midcap150/Smallcap250 universe (point-in-time membership, not survivorship-biased hand-picks) before concluding the strategy is dead.

**H5:** The strategy may have edge as a **relative-value/pairs construct** rather than a directional one — e.g., long the RS-turning-up underperformer vs. short a RS-turning-down sector peer, removing market beta entirely so the small excess-return signal isn't drowned out by broad index drift (which is what's happening above: baseline win rate is already 53-62% because Nifty itself trended up most of 2019-24).

**H6:** Our reconstructed RS21/RS55 (Mansfield oscillator: ratio vs SMA(ratio,n)) may not match the exact smoothing/lookback convention in the internal `stockedge_technical_indicators`/`ratio_charts_data` tables. Before discarding the idea, this needs to be re-tested against the real internal indicator values once DB access is available — a different smoothing constant changes signal timing and could change the conclusion.

## Recommendation to the team

1. **Do not proceed to a position-managed backtest, portfolio CAGR/Sharpe build-out, or satellite-strategy capital commitment on this signal as currently specified.** The honest finding is a null result on a reasonably-sized, multiply-cross-checked sample (large-cap NSE, 2019-24). Building elaborate stop-loss/sizing machinery on top of a signal with no detectable raw edge would be polishing noise — the classic quant-research failure mode of "the backtest looks great because we kept tuning the rules until it did."
2. **Specifically reject the "use 10% pa pledged-capital financing as a satellite strategy" plan for this signal.** Margin financing cost is a certain drag (10% pa); deploying it against a signal whose excess return is statistically indistinguishable from zero is negative expected value by construction, regardless of win rate, because the win rate observed here is mostly the market's own positive drift, not the signal.
3. **Before any further work, get access to the real `market_regime`, `ratio_charts_data`, `stockedge_technical_indicators` tables** (H6) and re-run this exact test — if the real internal indicators behave differently from our reconstruction, this conclusion could change.
4. **In parallel, test H4/H5** (broader/midcap universe, market-neutral pairs construction) since those are the two changes most likely to surface real edge if the underlying intuition (mean-reversion in relative strength) has any truth to it — it's far more plausible in less efficient names or with beta removed than in large-cap absolute-return form.
