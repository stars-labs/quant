> **Data refreshed 2026-06-08** (BTC $62,948, FNG=8 Extreme Fear) via the freqtrade-free
> `download_binance.py`. Re-run after the recent BTC drop: accumulator +376% ROI (now in
> deep-fear-boost), deployed Donchian ETH+BTC+SOL recent +22.6%/Sharpe 2.20/−10.1% (holds up),
> ETH+BTC EMA full +211%/2.41/−13.2%. Recent volatility did not degrade the deployed strategy.

# Strategy Leaderboard — Nautilus, all markets

Auto-updated by the `/loop … find best strategy` run. Each iteration tests a config/asset
on real data via the event-driven Nautilus ports and records the result here.
Metric notes: returns are single-asset, full available history, simple sizing (no leverage).
Risk-adjusted (Calmar) matters more than raw return.

## Crypto — trend (HonestTrend EMA72/144, FNG<80 gate) — asset × timeframe
| Asset | TF | entries | return (full hist) | notes |
|---|---|---|---|---|
| **ETH/USDT** | **1h** | 92 | **+119.1%** | 🏆 leader: ema72/144 adx25 (robust across adx15-25) |
| ETH/USDT | 1h | 39 | +110.4% | ema120/240 — also solid; slower=fewer trades |
| ETH/USDT | 15m | 343 | +70.5% | |
| **BTC/USDT** | **1h** | 25 | +48.2% | 1h beats 15m for BTC too |
| BTC/USDT | 15m | 121 | +27.8% | deployed to testnet prod (15m) |
| ETH/USDT | 4h | 15 | +27.5% | too few signals |
| BTC/USDT | 4h | 5 | −2.3% | too few signals |

**Finding:** 1h > 15m > 4h for BOTH BTC and ETH — the 1h timeframe (EMA72/144 ≈ 3d/6d
trend) is the generalizable sweet spot. The deployed testnet trend uses 15m → consider
switching to 1h.

**Leader risk-adjusted (ETH 1h ema72/144 adx25):** Sharpe **1.80**, Sortino 5.37, Profit
Factor 1.47, win rate 31.5% with ~6.4x payoff (avg win $6.2k vs avg loss $0.96k). Genuine
trend-following edge — not inflated raw return. Strong deploy candidate.

## Crypto — breakout (Donchian channel, ETH 1h) — VALIDATED at matched 10% sizing
| entry/exit lookback | entries | return @10% | Sharpe | notes |
|---|---|---|---|---|
| 168 / 72 | 167 | +46.9% | **2.71** | smoothest; single entry (no pyramid) |
| 96 / 48 | 262 | +49.7% | 2.24 | |

**Honest verdict (iter6's +2187% was a 95%-sizing illusion):** at MATCHED 10% sizing,
Donchian makes +47-50% vs EMA-cross's +119%. So:
- **Raw return: EMA-cross wins** (+119% > +47%) — its pyramid-on-winners compounds trends harder.
- **Risk-adjusted: Donchian wins** (Sharpe 2.71 > 1.80) — single-entry, smoother.
Different profiles. A higher-Sharpe engine can be sized up; best-of-both = Donchian + pyramid (next).

**Donchian + pyramid (iter8) — REJECTED:** +134.9% return but Sharpe **0.12** (collapsed).
Pyramiding stacks ~2.6x into one asset → return up, variance explodes. Pyramid is a
return↔smoothness tradeoff, not a free lunch. Notably EMA+pyramid keeps Sharpe 1.80 while
breakout+pyramid craters to 0.12 → EMA's entry timing pairs with pyramiding far better.

## Crypto — multi-asset trend portfolio (1h EMA72/144 adx25, shared account)
| portfolio | sizing | return | Sharpe | notes |
|---|---|---|---|---|
| **ETH + BTC** | 10% each | **+210.9%** | **2.41** | 🏆 BEST OVERALL — beats single-asset on BOTH dims |
| ETH only | 10% | +119.1% | 1.80 | |
| ETH+BTC+SOL+BNB | 5% each (~20% tot) | +291.6% | 2.20 | +return vs 2-asset, Sharpe plateaus |
| ETH+BTC+SOL+BNB | 7.5% each (~30%) | +679.0% | 2.16 | |
| ETH + BTC | 20% each | +676.6% | 1.70 | over-deployed → return↑ Sharpe↓ |

**Finding:** ETH+BTC diversification lifts BOTH return and Sharpe (2.41). Adding SOL+BNB at
the same ~20% total adds RETURN (+292%) but Sharpe plateaus/dips to ~2.20 — crypto majors
are all ~0.8 correlated + SOL adds vol, so marginal diversification fades. ~20% total is the
sweet spot. Best Sharpe = ETH+BTC (2.41); best return-at-risk = 4-asset (+292%/2.20).

## TRUE maxDD (iter13) — measured via an equity-curve Actor (USDT + position MTM per bar)
**ETH+BTC 1h @10% each: +210.9% / Sharpe 2.41 / TRUE maxDD = −13.2%** ✅ validated.

The iter11 −60%/−85% figures were a measurement bug (an.returns() cumprod). The honest maxDD
is only **−13%** — because the portfolio deploys just ~20% of equity and the trend exits cut
losers. Calmar ≈ 1.1 (vs BTC buy&hold's 0.64 with −76% DD). This is a genuinely strong,
low-drawdown strategy. Method: a lightweight Actor records total equity (USDT + Σ balance×close)
every bar → real drawdown. Use this Actor for all future DD numbers.

## Unified trend family — TRUE maxDD (iter15, all via EquityRecorder)
| config | return | Sharpe | TRUE maxDD | note |
|---|---|---|---|---|
| **ETH+BTC @10%** | **+211%** | **2.41** | **−13.2%** | 🏆 best balance |
| 4-asset @5% | +292% | 2.20 | −19.2% | most return, worst DD (SOL/BNB hurt tail) |
| ETH single @10% | +119% | 1.80 | −13.5% | |
| BTC single @10% | +49% | 4.08* | −10.6% | *Sharpe inflated by sparse trading (25 trades, mostly flat) |

All trend DDs are a healthy −10% to −19% (NOT the retracted −60%). ETH+BTC is the pick.

**iter16 — gold (PAXG) diversifier didn't help:** ETH+BTC+GOLD = +218%/2.30/−13.2% (DD
unchanged). Trend-on-gold is flat most of the time (gold barely trends: GOLD-only +5%),
so it's NOT positioned during crypto crashes → no hedge. Lesson: adding more TREND sleeves
can't lower DD below ~−13%; a real hedge needs a STATIC/counter-cyclical allocation, not
another trend sleeve. The crypto-trend DD floor is ~−13%. **Crypto search has converged →
ETH+BTC 1h multi-asset trend is the winner. Real cross-asset diversification needs equities (Mon IB).**

## iter17 — static gold hedge + CONVERGENCE
ETH+BTC trend +30% static PAXG hold = +231% / 2.46 / −13.2% (DD unchanged, +20% free return).
The −13% DD floor won't move because the strategy under-deploys (~20% in market, rest cash)
— it's structurally low-DD; there's little DD to cut. The earlier "high DD problem" was the
−60% measurement bug, not real.

## iter18 — mean-reversion (RSI oversold) — REJECTED (wrong family for crypto)
Rough test (results identical across RSI thresholds + nan Sharpe → implementation suspect,
don't trust exact #s) but directionally clear: ~−65% maxDD vs trend's −13%. MR buys "oversold"
into crypto downtrends = catching falling knives. Crypto strongly trends → trend ≫ mean-reversion.
Confirms the trend family is correct for crypto.

## 🚩 iter19 — ROBUSTNESS CHECK FAILS: the edge has DECAYED (most important finding)
Split ETH+BTC trend into time halves:
| period | return | Sharpe | maxDD |
|---|---|---|---|
| 1st half (early ~2020-22) | +166% | 4.47 | −13% |
| **2nd half (recent ~2023-26)** | **+11%** | **−2.13** | −6.6% |

**The +211% is almost entirely an early-regime artifact.** In recent years the EMA-trend
edge has largely decayed — recent-half Sharpe is NEGATIVE (−2.13). Crypto 2023-26 is
choppier/more efficient → trend-following gets whipsawed. **Deploying on the full-history
+211% would be deploying a decayed edge.** This is the #1 takeaway of the whole search:
the full-history headline overstates forward expectancy.

## ✅ iter20 — Donchian breakout SURVIVES the recent regime (rescues the trend approach)
Recent-half (2023-26) only:
| strategy | recent return | recent Sharpe | maxDD |
|---|---|---|---|
| **Donchian 168/72 1h** | **+17.2%** | **+2.10** | −9.4% |
| EMA-cross 72/144 1h | +11% | −2.13 | −6.6% |

**Breakout is robust where EMA-cross decayed.** Donchian waits for a confirmed new high
(filters chop); EMA-cross reacts to every crossover (whipsawed in choppy 2023-26). →
For forward deployment, prefer **Donchian breakout over EMA-cross**. (Recall iter7: at
matched sizing Donchian had lower full-history return but higher Sharpe — now we see WHY:
its edge persists into the recent regime while EMA's faded.)

### iter21 — Donchian recent-regime param robustness (CONFIRMED deployable)
Recent-half ETH+BTC Donchian, 10% each, multiple lookbacks:
| lookback | recent return | Sharpe | maxDD |
|---|---|---|---|
| 168/72 | +17.2% | 2.10 | −9.4% |
| 96/48 | +10.1% | 1.22 | −7.5% |
| 240/96 | +9.7% | 1.29 | −8.5% |

All 3 positive (Sharpe 1.2-2.1) → robust, not a single-param fluke. Modest (~4% CAGR over
~3y) but REAL in the current regime — honest forward expectation for crypto trend now.

## ✅✅ FINAL DEPLOYABLE ANSWER (crypto) — confirmed iter24
**ETH+BTC+SOL · 1h Donchian breakout (168/72) · ~6.67% each (~20% total)**
Recent out-of-sample (2023-26): **+22.6% / Sharpe 2.20 / −10.1% maxDD** (at ≤0.1% fees).
Beats ETH+BTC (+17%/2.10) by adding SOL and dropping range-bound BNB. Honest forward
expectation: ~mid-single-digit CAGR, low DD, positive Sharpe — IF execution cost ≤0.25%.
This is the validated, robustness-checked, cost-aware crypto winner. (Earlier EMA +211%
was an early-regime mirage.)

---
### (superseded) earlier framing:
**ETH+BTC 1h Donchian breakout (168/72, 10% each)** — recent-regime validated:
+17% / Sharpe 2.10 / −9% DD on out-of-sample recent data. Use THIS, not the EMA-cross
(whose +211% full-history was an early-regime mirage that's since decayed to Sharpe −2.13).
Forward expectation: modest (~mid-single-digit CAGR), low DD, positive Sharpe. Crypto
trend-following is structurally harder in 2023-26; size accordingly.

**iter22 — fee sensitivity (the edge is THIN):** recent Donchian return by round-trip cost:
0.10%→+15.6%, 0.25%→+10.3%, 0.50%→+2.1% (nearly dead). The recent edge survives ONLY at
low execution cost (≤0.25%): use low-fee tier / BNB discount / limit orders, not naive
market orders with slippage. ~4% gross CAGR has little room for costs. Deploy-viability is
execution-cost-gated.

## iter23 — breakout is ASSET-SELECTIVE (trenders yes, range-bound no)
Recent-half Donchian per coin: ETH/BTC Sharpe 2.10, **SOL +17%/Sharpe 2.71**, **BNB −3%/Sharpe −0.31**.
Breakout works on coins that trend (ETH/BTC/SOL) and FAILS on range-bound ones (BNB, an
exchange token). 4-coin incl. BNB → Sharpe 1.74 (dragged down). **Refined deployable set:
ETH+BTC+SOL (drop BNB).** Asset selection > blindly adding coins.

## 🏁 CRYPTO SEARCH CONVERGED (with the decay caveat)
Best full-history config: **ETH+BTC 1h multi-asset trend** → +211% / Sharpe 2.41 / −13% maxDD,
BUT recent-half edge is weak/negative. Before any real deployment: re-validate on recent data
only, and size DOWN / treat as regime-dependent. Exhausted families: trend (best but decaying),
breakout (≈trend), mean-reversion (catches knives), accumulation (rides BTC), options (mediocre).
**Next real edge = US equities (Mon IB).**

## Current best by objective (with the honest DD caveat)
- **OVERALL ✅:** ETH+BTC 1h multi-asset trend, 10% each → **+211% / Sharpe 2.41 / −13.2% maxDD** (validated)
- **Return-focused single:** ETH 1h EMA+pyramid → +119% / Sharpe 1.80
- **Smoothness single:** ETH 1h Donchian 168/72 → +47% / Sharpe 2.71

## 2026-09-27 — house universe screen (Donchian 1h 168/72) — 3 → 13 assets
`scripts/screen_universe.py`. Binance top-30 USDT pairs by volume. **Selected on in-sample
2024-01-01..2025-12-31 only**, criteria fixed before looking at 2026: two full years of data, net
return > 0 (0.1%/side), strategy maxDD shallower than buy-and-hold's, return/|maxDD| ≥ 0.5.
Selected (13): BTC ETH SOL XRP DOGE ADA AVAX SUI NEAR UNI ZEC PEPE WLD. Rejected by criteria: BNB
(ret/DD 0.28), LINK, ARB, DASH, QNT, RUNE, LTC, RARE, FIL; too short a history: ENA TAO SAGA BABY
MUBARAK XPL PUMP GRAM.

| out-of-sample 2026-01-01..09-26 | strategy (eq-wt) | buy&hold | strat maxDD | hold maxDD | beat hold |
|---|---|---|---|---|---|
| **selected 13** | **+48.5%** | +34.2% | −31.3% | −59.4% | 9/13 |
| rejected 9 | +24.6% | +31.0% | −35.3% | −56.2% | 3/9 |
| old house set BTC/ETH/SOL | +5.0% | −5.4% | −25.0% | −51.3% | 3/3 |

Means are pulled up by ZEC (+302%); medians of the selected: strategy +6.6% vs hold −3.8%. The
selection discriminates out of sample (selected beat hold 9/13, rejected 3/9) and halves drawdown.
Losers kept honestly: WLD −56%, DOGE −23%, AVAX −13%. Deployed as `strategy_record.ASSETS`
(public /record backfilled from 2026-01-01, labelled 回溯). Re-screen yearly on a fresh in-sample.

## 2026-09-27 — funding carry (spot long + perp short) — VERDICT: not an opportunity now
`scripts/funding_carry_backtest.py`, Binance funding 2024-01-01..2026-09-26, today's top-40 spot-listed
perps (survivorship caveat). Costs 0.40%/round trip (4 taker fees + spread). Annualised ON NOTIONAL;
with 1:1 collateral (no-liquidation setup) the return on capital is HALF.

| variant | 2024 | 2025 | 2026 YTD | full | maxDD |
|---|---|---|---|---|---|
| BTC always-on | +11.7% | +5.1% | +2.7% | +6.9% | −0.4% |
| ETH always-on | +12.8% | +4.9% | +1.6% | +6.9% | −0.6% |
| SOL always-on | +13.4% | +0.4% | −1.4% | +4.7% | −2.6% |
| weekly top-3 by trailing funding (>10%) | +11.7% | −1.7% | −3.9% | +2.6% | −6.4% |
| weekly top-5 (>20%) | +13.3% | +2.1% | 0.0% | +5.6% | −0.8% |
| weekly top-10 (>10%) | +6.6% | −3.6% | −5.5% | −0.4% | −9.0% |
| per-coin threshold 20%/5% (39 coins, mean) | | | | +2.7% | |

Only the 2024 bull-market froth paid (~12% on notional, ~6% on capital). In 2026 the majors' carry is
~1-1.5% on capital (below idle stablecoin yield) and chasing high funding LOSES after fees — high
funding mean-reverts within days and turnover (~50x/yr) eats it. Product consequence: /scan and the
daily digest present funding as a crowding/sentiment gauge with these numbers, not as a carry call.
Revisit if BTC/ETH trailing funding returns to 2024 levels (>15%/yr sustained).

## 2026-09-27 — daily Donchian breakout on US equities + commodities — VERDICT: no trigger
`scripts/screen_daily_breakout.py` (protocol fixed in its docstring before OOS). Long-only, next-day
fill, 0.05%/side equities, 0.10%/side commodities; 15 Donchian N/M + 3 MA-filter variants; in-sample
pick = best equal-weight Calmar; trigger bar = OOS net > 0, Calmar ≥ hold's, beats hold on ≥ half.

| universe | IS pick | OOS 2024-01..2026-09 strategy | buy&hold | beat hold |
|---|---|---|---|---|
| 48 US equities (IS 2014–2023) | Donchian 100/50 | +106.6%, CAGR 30.4%, maxDD −25.8%, Calmar 1.18 | +261.1%, CAGR 60.1%, maxDD −36.3%, Calmar 1.65 | 10/46 |
| 12 commodity futures (IS 2017–2023) | Donchian 252/10 | +0.9%, maxDD −15.2%, Calmar 0.02 | +51.8%, maxDD −29.3%, Calmar 0.56 | 0/12 |

Fails both. /scan equity + commodity tabs therefore show observations only (52-week high distance,
200-day MA, 1-month return, VIX, breadth), no trigger wording. Caveats: semis list chosen with 2026
hindsight; Yahoo closes not dividend-adjusted; continuous futures not roll-adjusted.

## Crypto — accumulation (fear-driven DCA)
| Variant | avg cost vs naive | ROI | notes |
|---|---|---|---|
| smart fear+dip DCA | −9.6% cost basis | +360% (through 2026-06 dip) | deployed testnet prod |

## Crypto — options (put-selling, free Tardis Deribit data 2019-2026)
| Variant | CAGR | maxDD | Calmar | notes |
|---|---|---|---|---|
| short-DTE (5-12d) put-sell | +7.4% | 7.6% | **0.97** | best risk-adj; synergy w/ accumulator cash |
| deepOTM put-sell | +10.0% | 19.5% | 0.51 | |
| naked CSP | +6.0% | 32.5% | 0.19 | |
| BTC buy&hold (benchmark) | +49.4% | 76.6% | 0.64 | nothing beats holding on raw return |

## Benchmarks to beat
- BTC buy&hold: +49% CAGR / 76.6% DD / Calmar 0.64
- Risk-adjusted bar: Calmar ~1.0 (short-DTE puts)

## Queue / ideas to test next
- [x] trend timeframe sweep on ETH → 1h wins (+116%)
- [x] BTC trend on 1h → yes, +48% > 15m's +28%; 1h generalizes
- [x] ETH 1h param sweep → ema72/144 adx25 best (+119%); 48/96 overtrades (cliff to 28%)
- [x] risk-adjusted for leader → Sharpe 1.80 / Sortino 5.37 (via engine.get_result)
- [x] Donchian breakout vs EMA → breakout Sharpe 2.71 > 1.80 (but sizing-inflated %)
- [x] Donchian @ matched 10% → +47% Sharpe 2.71 vs EMA +119% Sharpe 1.80 (sizing illusion debunked)
- [x] Donchian + pyramid → REJECTED (+135% but Sharpe 0.12; variance explodes)
- [x] multi-asset ETH+BTC → +211%/Sharpe 2.41, beats single on BOTH (best overall)
- [x] SOL/BNB added (4-asset) → +292%/Sharpe 2.20: more return, Sharpe plateaus (majors correlated)
- [x] maxDD attempt → RETRACTED (an.returns() cumprod is not true equity DD; stop-insensitive)
- [x] equity-curve Actor → TRUE maxDD −13.2% (iter11's −60% was a bug); strategy validated
- [x] committed leaderboard + equity_recorder.py + run_portfolio_trend.py (ac7b3a6)
- [x] unified TRUE maxDD for trend family: all −10% to −19% (ETH+BTC −13% best balance)
- [x] gold (PAXG) as trend sleeve → no DD help (flat during crashes; trend≠hedge)
- [ ] crypto search CONVERGED — winner = ETH+BTC 1h trend. Next genuine edge = equities (Mon IB)
- [ ] (optional) static gold/cash hedge overlay to cut the −13% floor
- [ ] DEPLOY: ETH+BTC 1h multi-asset trend (+211%/2.41/−13%) is the clear winner
- [ ] DEPLOY: multi-asset ETH+BTC 1h trend is the validated winner — switch testnet trend to it
- [ ] ETH/BNB/SOL accumulation (vs BTC) — need BNB/SOL data
- [ ] short-DTE put-sell on ETH (vs BTC)
- [ ] US equities (semis) trend — pending IB Mon
- [ ] DEPLOY CANDIDATE: ETH 1h trend to testnet prod (after a few more validations)

---

## US Equity (HonestTrend, real IB data) — 2026-06-09

EMA-pair grid for `HonestTrendEquity` on **real split/dividend-adjusted IB bars**
(NVDA/AMD/QQQ, ~2023-06 → 2026-06; 750 daily / 5226 hourly each). $100k CASH account,
ADX>18, vol>SMA20, −8% exchange-side stop, VIX>30 regime block. Metrics from a daily
realized-cash equity curve (Sharpe annualized 252d; Calmar = CAGR/|maxDD|). Runner:
`nautilus_equity/grid_honest_equity_real.py`.

### 1-DAY bars
| EMA     | asset | fills | ret %  | maxDD% | Sharpe | Calmar |
|---------|-------|------:|-------:|-------:|-------:|-------:|
| 20/50   | NVDA  | 16    | +33.98 | 29.31  | 2.59   | 0.35   |
| 20/50   | AMD   | 15    | +42.62 | 29.44  | 2.84   | 0.43   |
| 20/50   | QQQ   | 4     |  +2.40 | 27.03  | 1.52   | 0.03   |
| 30/60   | NVDA  | 6     | +39.47 | 27.97  | 3.77   | 0.48   |
| 30/60   | AMD   | 4     | +22.58 | 28.42  | 3.52   | 0.25   |
| 30/60   | QQQ   | 8     |  +4.64 | 26.97  | 1.66   | 0.06   |
| 50/100  | NVDA  | 4     |  +3.84 | 27.87  | 1.75   | 0.05   |
| 50/100  | AMD   | 6     | +67.53 | 28.58  | 4.40   | 0.66   |
| 50/100  | QQQ   | 0     |  +0.00 |  —     | —      | —      |
| 72/144  | NVDA  | 0     |  +0.00 |  —     | —      | —      |
| 72/144  | AMD   | 2     |  −0.79 |  9.92  | 0.11   | −0.06  |
| 72/144  | QQQ   | 4     |  +7.79 | 27.30  | 2.26   | 0.09   |

### 1-HOUR bars
| EMA     | asset | fills | ret %  | maxDD% | Sharpe | Calmar |
|---------|-------|------:|-------:|-------:|-------:|-------:|
| 20/50   | NVDA  | 37    |  +4.71 | 30.04  | 3.02   | 0.05   |
| 20/50   | AMD   | 76    | +23.27 | 29.96  | 3.66   | 0.25   |
| 20/50   | QQQ   | 37    |  +1.54 | 18.40  | 2.36   | 0.03   |
| 30/60   | NVDA  | 50    |  +8.06 | 28.06  | 3.20   | 0.09   |
| 30/60   | AMD   | 56    | +46.13 | 30.67  | 4.71   | 0.44   |
| 30/60   | QQQ   | 23    |  +0.50 | 17.75  | 2.16   | 0.01   |
| 50/100  | NVDA  | 26    | +13.38 | 30.78  | 4.01   | 0.14   |
| 50/100  | AMD   | 27    | +15.33 | 31.76  | 4.35   | 0.18   |
| 50/100  | QQQ   | 19    |  +6.67 | 26.74  | 3.60   | 0.08   |
| 72/144  | NVDA  | 33    | +29.83 | 28.94  | 4.90   | 0.35   |
| 72/144  | AMD   | 17    |  −3.36 | 31.76  | 2.53   | −0.04  |
| 72/144  | QQQ   | 16    |  +3.73 | 26.84  | 3.28   | 0.05   |

### Robustness (mean across NVDA/AMD/QQQ)
| tf     | EMA    | avg ret% | avg fills | avg maxDD% | avg Sharpe | min Sharpe |
|--------|--------|---------:|----------:|-----------:|-----------:|-----------:|
| 1-DAY  | 20/50  | +26.33   | 11.7      | 28.59      | 2.32       | 1.52       |
| 1-DAY  | 30/60  | +22.23   | 6.0       | 27.78      | 2.98       | 1.66       |
| 1-DAY  | 50/100 | +23.79   | 3.3       | 18.82      | 2.05       | 0.00       |
| 1-DAY  | 72/144 |  +2.33   | 2.0       | 12.40      | 0.79       | 0.00       |
| 1-HOUR | 20/50  |  +9.84   | 50.0      | 26.13      | 3.01       | 2.36       |
| 1-HOUR | 30/60  | +18.23   | 43.0      | 25.50      | 3.36       | 2.16       |
| 1-HOUR | 50/100 | +11.79   | 24.0      | 29.76      | 3.99       | 3.60       |
| 1-HOUR | 72/144 | +10.07   | 22.0      | 29.18      | 3.57       | 2.53       |

### Recommendation → **1-HOUR EMA 50/100** (deployed default)
Chosen for **robustness over peak return**:
- Every asset is **profitable** (NVDA +13.4%, AMD +15.3%, QQQ +6.7%) — no zero-entry /
  negative-return asset (50/100 daily skips QQQ entirely; 72/144 zeroes NVDA daily and
  goes negative on AMD hourly; 20/50 daily barely trades QQQ at +2.4%).
- **Highest min-Sharpe of any config (3.60)** and highest avg Sharpe among the hourly
  grid (3.99) — the metric we actually care about (worst-asset risk-adjusted).
- Moderate turnover (~24 fills/asset over 3y) — trades meaningfully but is **not**
  over-trading like 20/50-hourly (50 fills) and is statistically far less single-trade
  -dependent than the 2–6-fill daily configs (a 3-year daily backtest with 4 fills is
  basically un-validatable → that's the curve-fit trap).
- On hourly bars 50/100 is a *moderate* (not extreme-fast) crossover → lower curve-fit
  risk than 20/50, while still firing often enough on hourly to be statistically real.

Caveats: maxDD ~30% (asset volatility — NVDA/AMD are high-beta semis; the −8% per-position
stop limits per-trade loss, not portfolio DD). Sharpe is computed on a *realized-cash*
curve (flat between fills), so absolute Sharpe is optimistic; treat the numbers as
**relative** rankings across configs, which is what drove the choice. Backtest is on 3
correlated semis/QQQ over a single (largely bull) 3y window — paper-trade before any size.

Runner-up: **1-DAY EMA 30/60** if a low-touch daily cadence is preferred (all 3 assets
positive, avg Sharpe 2.98) — but only ~6 fills/asset makes it fragile.

## 2026-09-27 — regime/range filter on the house Donchian rule — VERDICT: don't adopt
`scripts/research_trend_filter.py`. Motivation: the live rule's win rate is ~38%, most losses are
false breakouts in ranging markets. Tested 6 simple filter families (3 pre-chosen parameter values
each, no fine grid search) **on top of** the existing entry (`close > max HIGH of prior 168 bars`);
the exit (`close < min LOW of prior 72 bars`) was never touched. 18 variants + baseline = 19 runs,
**pre-registered in-sample 2022-01-01..2025-12-31** (as much history as each coin has; SUI/PEPE/WLD
start later), **out-of-sample 2026-01-01..09-27**, same 13 coins as `sr.ASSETS`, net of 0.1%/side fees.

Families: `trend_self`/`trend_btc` (entry also needs close > SMA of last N days, N∈{100,150,200},
self or BTC-as-macro-gate), `strength` (breakout must clear the channel by x∈{0.5%,1%,2%}),
`atr_breakout` (clear it by k∈{0.25,0.5,1.0}×ATR14d), `cooldown` (no re-entry for C∈{24,72,168}h
after a losing exit), `entry_lb` (widen the breakout lookback itself to L∈{216,264,336}h).

### In-sample sweep (2022-01-01..2025-12-31, mean/median across coins with enough history)
| variant | mean ret | median ret | win rate | mean maxDD | beats baseline | trades |
|---|---|---|---|---|---|---|
| **baseline (unfiltered)** | **+229.7%** | +155.6% | 37.5% | −45.4% | — | 854 |
| trend_self_100d | +183.2% | +164.1% | 38.8% | −40.8% | 7/13 | 584 |
| trend_self_150d | +151.1% | +100.4% | — | −43.6% | 4/13 | 553 |
| trend_self_200d | +181.3% | +84.5% | — | −41.0% | 1/13 | 565 |
| trend_btc_100d/150d/200d | +14–27% | — | 32–44% | −8 to −15% | ≤2/13 | 90–131 |
| strength_0.5/1.0/2.0pct | +138–237% | — | 38–41% | −40 to −44% | ≤5/13 | 367–749 |
| atr_k 0.25/0.5/1.0 | +181–231% | — | 37–39% | −42 to −45% | ≤6/13 | 558–801 |
| cooldown_24h | +227.4% | +155.6% | 38% | −45.4% | 1/13 | 853 |
| **cooldown_72h** | +221.6% | +149.4% | **37.76%** | −44.9% | **8/13** | 830 |
| cooldown_168h | +220.0% | +161.9% | 37% | −43.9% | 6/13 | 782 |
| entry_lb_216/264 | +163–175% | — | 37–38% | −40 to −45% | ≤6/13 | 661–754 |
| entry_lb_336 | +191.3% | +117.4% | 38.9% | −40.6% | 7/13 | 552 |

Pre-registered selection rule: keep only variants that (a) beat the unfiltered rule's per-coin
return on ≥8/13 coins (majority, not just the aggregate) **and** (b) raise the mean win rate; among
survivors pick the best return/|maxDD|. Only **`cooldown_72h`** clears both bars — and only just:
win rate 37.76% vs baseline's 37.48% (+0.3pp), mean return −0.8pp vs baseline. The two variants with
a materially bigger win-rate lift, `entry_lb_336` (38.9%) and `trend_self_100d` (38.8%), both land at
7/13 coins beaten — one coin short of the majority bar. `trend_btc` (macro BTC-regime gate) cuts
trade count by 85–90% and return by ~90%: far too restrictive to be useful.

### Out-of-sample 2026-01-01..09-27 — cooldown_72h vs unfiltered vs buy&hold
| asset | unfiltered | filtered | hold | unfilt maxDD | filt maxDD | unfilt N | filt N | unfilt win | filt win |
|---|---|---|---|---|---|---|---|---|---|
| BTC | +6.6% | +6.6% | −3.8% | −17.3% | −17.3% | 14 | 14 | 29% | 29% |
| ETH | −6.6% | −6.6% | −9.5% | −24.0% | −24.0% | 14 | 14 | 50% | 50% |
| SOL | +14.6% | +14.6% | −3.2% | −33.6% | −33.6% | 12 | 12 | 42% | 42% |
| XRP | −0.9% | +3.4% | −17.6% | −19.2% | −15.7% | 13 | 12 | 31% | 33% |
| DOGE | −23.6% | −32.6% | −18.3% | −42.3% | −49.1% | 15 | 15 | 27% | 20% |
| ADA | +6.3% | +6.3% | −24.5% | −26.5% | −26.5% | 14 | 14 | 43% | 43% |
| AVAX | −12.6% | −8.4% | −12.7% | −38.8% | −35.9% | 14 | 13 | 36% | 38% |
| SUI | +36.3% | +36.3% | −16.7% | −30.5% | −30.5% | 14 | 14 | 36% | 36% |
| NEAR | +115.6% | +115.6% | +233.5% | −36.0% | −36.0% | 16 | 16 | 56% | 56% |
| UNI | +132.7% | +132.7% | +71.7% | −31.5% | −31.5% | 11 | 11 | 64% | 64% |
| ZEC | +300.3% | +300.3% | +221.5% | −30.1% | −30.1% | 13 | 13 | 46% | 46% |
| PEPE | +109.9% | +130.4% | +7.2% | −14.0% | −6.6% | 11 | 10 | 64% | 70% |
| WLD | −56.1% | −59.1% | +9.0% | −62.6% | −63.1% | 18 | 17 | 33% | 29% |
| **mean (13)** | **+47.9%** | **+49.2%** | +33.6% | −31.3% | −30.8% | 179 | 175 | 43% | 43% |

Filter beats unfiltered on **3/13 coins** (XRP, AVAX, PEPE), ties on 8/13 (cooldown never triggered
— no losing exit was followed by a fresh signal within 72h), and is **worse** on 2/13 (DOGE, WLD).
Aggregate mean return is +1.3pp higher, entirely carried by PEPE (+130% vs +110%); win rate is
identical (43%) to 1dp. Both beat buy&hold's mean (+33.6%, −59.4% maxDD) comfortably — that's the
universe screen's edge, not this filter's. The two in-sample near-misses don't hold up out-of-sample
either: `entry_lb_336` beats unfiltered on only 5/13 coins and drags mean return down to +35.0%;
`trend_self_100d` beats on 8/13 but mean return is flat (+46.0% vs +47.9%) — a wash, not an edge.

### Per-year breakdown (equal-weight mean return across qualifying coins, unfiltered vs cooldown_72h)
| year | coins | unfiltered | cooldown_72h | buy&hold |
|---|---|---|---|---|
| 2022 | 10 | −15.8% | −16.6% | −72.9% |
| 2023 | 12 | +70.7% | +75.9% | +153.3% |
| 2024 | 13 | +171.5% | +158.1% | +216.4% |
| 2025 | 13 | +7.9% | +5.5% | +14.8% |
| 2026 YTD | 13 | +47.9% | +49.2% | +33.6% |

No consistent direction: the filter helps in 2023 and 2026, hurts in 2022/2024/2025, always by a
few points — noise, not signal.

### Aug-2026 rally check
All 13 coins under `cooldown_72h` still opened a fresh entry inside Aug 2026 (the rally the "wealth
effect" product loop relies on is not filtered out) — expected, since a 72h post-loss cooldown is a
narrow, temporary gate, not a regime block.

### VERDICT: don't adopt
None of the 18 simple variants clears a real robustness bar. The mechanical pre-registered winner,
`cooldown_72h`, technically passes the selection rule in-sample but by a margin indistinguishable
from noise (+0.3pp win rate, 8/13 — barely a majority), gives back return in-sample, ties or loses on
10/13 coins out-of-sample, and flips sign across years with no discernible pattern. The two filters
that target the stated failure mode most directly and show the biggest win-rate lift in-sample
(`entry_lb_336`, `trend_self_100d`) miss the coin-majority bar and don't hold up out-of-sample either.
**No change to `strategies/strategy_record.py`'s `step()`.** Had `cooldown_72h` been adopted despite
the marginal case, it would mean: after a losing exit, `step()` withholds re-arming the entry check
(the `close > max(HIGH of prior 168 bars)` test) for the next 72 hourly bars, win or lose thereafter
unaffected — but the numbers above don't justify carrying that extra state and parameter. Re-open
this only if a future re-screen (or a different fee/liquidity regime) changes the false-breakout
picture; don't re-litigate with a finer grid on the same data — that's the overfitting trap this
sweep was built to avoid (19 variants tried, reported above, not cherry-picked post hoc).
