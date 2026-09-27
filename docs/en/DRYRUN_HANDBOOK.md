# Dry-Run Operations Handbook — HonestTrend Family

**This is the doc for your daily 5-minute glance.**
For the full technical analysis, see [`HONEST_TREND_REPORT.md`](HONEST_TREND_REPORT.md) and [`PHASE_B_FUTURES_SHORT.md`](PHASE_B_FUTURES_SHORT.md).

> **2026-04-22 architecture update**: Adopted Phase A (BTC→DCA, trend → ETH/BNB/SOL alts) + Phase B (futures L+S hedging). The pair list and port assignments below reflect the latest state.

---

## 1. Currently running bots (3 dry-runs in parallel)

| Strategy | Config | Market | Direction | Pairs | Port |
|------|--------|--------|------|-------|-----:|
| `HonestTrend15mDry` | `config_dryrun_honest15m.json` | spot | long-only | ETH/BNB/SOL | 8082 |
| `HonestTrend1mMTF` | `config_dryrun_honest1mmtf.json` | spot 1m+4h gate | long-only | ETH/BNB/SOL | 8083 |
| `HonestTrendFutures` | `config_dryrun_honestfutures15m.json` | **futures** | **long+short** | ETH/BNB/SOL | **8084** |

All three share parameters:
- Parent class `HonestTrendGeneric`
- Simulated capital **10,000 USDT**
- Max concurrent positions: 3
- Stake 1500 USDT/trade (up to 3900 after pyramid)
- SQLite DB `user_data/tradesv3_<name>_dryrun.sqlite`
- Log directory `logs/<name>_dryrun_*.log`

**BTC is not in the trend pool** — BTC alpha is accumulated via the Smart DCA dual-channel system (see the last section).

---

## 2. Strategy logic (signal rules)

### Entry (buy only when **all 6 conditions are met**)

1. **EMA golden cross**: EMA(94, 15m) crosses above EMA(139, 15m)
   - 94 × 15m candles = 23.5 hours
   - 139 × 15m candles = 34.75 hours
   - Ratio 1.48x (not the classic 2x; Stage 1-3 validated this ratio as more robust)
2. **+DI > −DI** (trend direction confirmation)
3. **ADX > 18** (sufficient trend strength)
4. **Volume > past 24h average** (volume confirmation)
5. **Fear & Greed index FnG < 80** (the only data-validated sentiment defense rule)
6. Current bar volume > 0 (non-empty bar)

### Exit (sell on **any trigger**)

1. **EMA death cross**: EMA(94) crosses below EMA(139)
   - Also requires holding time ≥ 12 hours (to avoid 15m noise triggers)
2. Manual force exit (Telegram `/forcesell`)
3. **Stoploss**:
   - Spot bots (15mDry / 1mMTF): **no stoploss** (`stoploss = -0.99`). Stage 1 proved tight stops wipe out the trend-following edge
   - Futures bot: **−8% hard stoploss** (futures can't run naked like spot — must prevent liquidation)
4. Risk control: account-level drawdown kill-switch in `risk_manager.py` (15% pause / 20% retire)

### Futures short exclusive rules

Only `HonestTrendFutures` goes short:
- **Short entry**: EMA death cross + `minus_di > plus_di` + ADX > 18 + FnG **< 70**
- **FnG > 70 forbids shorts** (don't get squeezed during euphoria)
- **FnG < 30 softly amplifies** (panic-bottom shorts are highly efficient)
- **Leverage 1x** (no liquidation risk, pure directional alpha)
- **Funding cost**: roughly 4% annualized drag (included in backtest)

---

## 3. Expected metrics (what you'll see next)

Based on 2024-01 to 2026-04 backtest (OOS segment 2025-07 to 2026-04):

| Metric | Expected range |
|------|---------|
| Trades per week | **1–3** (approx) |
| Trades per month | 4–10 |
| Average hold per trade | **2–3 days** |
| Win rate | **35–45%** (typical 40%) |
| Average winning trade | +3% to +10% |
| Average losing trade | −1% to −4% |
| Worst single trade | **−23%** (historical extreme, 1% probability) |
| Longest losing streak | **7 trades** (historical extreme) |
| Monthly P&L variance | Very high — **monthly losses are allowed**; look at rolling 6-month PF |

### Typical trade flow after a trigger

```
[Telegram: Entry Fill] BTC/USDT at 93,250 USDT — 3,160 USDT stake (trend_15m tag)
    ↓
  (hold 2–3 days, EMA 94 stays above EMA 139)
    ↓
[Telegram: Exit Fill] BTC/USDT at 95,800 USDT — +2.7% profit (trend_exit tag)
```

---

## 4. Daily 5-minute checklist

**Daily** (1 minute):
- [ ] Scan Telegram — any `🚨 Risk State Change` alert?
  - None → carry on. Yes → go straight to §7
- [ ] Any Entry/Exit notifications? Roughly matching expected frequency (1-3/week)?

**Weekly** (3 minutes):
```bash
# Check current status
python $PROJECT_DIR/scripts/risk_monitor.py status

# Or send /status to the bot on Telegram — it will reply with:
#   Current balance / Open trades / Total profit
```

Expected to see:
- Status: `ACTIVE`
- Drawdown: **< 10%** (normal); 10-15% → be alert; ≥15% → auto PAUSE
- Rolling PF (50 trades): **> 1.2** mid/late; ≥1.0 early accumulation; <1.0 alert

**Monthly** (10 minutes):
- The 1st at 06:00 auto-runs walk-forward check; Telegram alerts if <50% of windows profitable
- Proactive comparison: live dry-run stats vs latest walk-forward backtest
  ```bash
  curl -s http://127.0.0.1:8082/api/v1/profit | jq
  ```

---

## 5. What messages will you see on Telegram

### Freqtrade bot itself (sent by HonestTrend15mDry)

| Trigger | Example |
|------|------|
| Startup | `Exchange: binance / Timeframe: 15m / Strategy: HonestTrend15mDry` |
| Entry (order placed) | `Buying BTC/USDT at 93250 USDT, tag: trend` |
| Entry filled | `New trade filled BTC/USDT at 93250 USDT — 3160 USDT stake` |
| Exit | `Selling BTC/USDT at 95800 USDT — +2.7% profit, tag: trend_exit` |
| Exit filled | `Trade closed BTC/USDT: +2.7% (+86 USDT)` |
| Warning | `Dry run is enabled. All trades are simulated.` (once at startup) |
| Protection triggered | A pair is cooled down (current strategy has no protection configured, so this won't fire) |

Interactive commands (send to the bot):
- `/status` — current open positions
- `/profit` — cumulative P&L
- `/daily` / `/weekly` / `/monthly` — periodic stats
- `/trades` — recent trades list
- `/performance` — per-pair performance
- `/balance` — simulated wallet balance
- `/forceexit <trade_id>` — force-close a trade (works in dry-run too)
- `/stopentry` — pause new entries (does not affect existing positions)
- `/help` — full command list

### Risk Monitor (sent by `scripts/risk_monitor.py` every 4h)

**Only sends on state change**; won't spam under normal conditions.

| Trigger | Message style |
|------|---------|
| DD first reaches ≥ 15% | `🚨 Risk State Change: ACTIVE → PAUSED. Drawdown 15.2% ≥ 15%...` |
| DD recovers to <10% | `🚨 Risk State Change: PAUSED → ACTIVE. Drawdown recovered to 9.0%...` |
| DD ≥ 20% | `🚨 Risk State Change: ACTIVE → RETIRED. Drawdown 21.3% ≥ 20%. Manual reset required.` |
| 6 months + PF<1.2 | `🚨 Risk State Change: ACTIVE → RETIRED. After 180d live, rolling PF 1.10 < 1.20.` |
| Manual pause/retire | `⏸ Manual PAUSE` / `🛑 Manual RETIRE` |

### Walk-Forward (1st of each month 06:00, `scripts/walk_forward_check.py`)

| Health | Message |
|--------|-----|
| ≥50% windows profitable | No alert (silent pass) |
| <50% windows profitable | `⚠️ EDGE DEGRADING: <50% windows profitable` |
| 0/4 windows profitable | `🚨 EDGE DEAD: 0 windows profitable. Consider retiring.` |

### KOL Alerts (independent of this strategy, `strategies/telegram_alerts.py`)

Runs every 30 minutes. **New fix**: every alert is now a clickable link → jumps to the original Google News article for verification.

```
🟢 TRUMP (+0.50)
[Trump endorses crypto at rally](https://news.google.com/rss/articles/...)
```

---

## 6. What counts as "normal"?

### ✅ All of these are normal (don't panic)

- **No trades for 1-2 weeks in a row** — EMAs haven't crossed; market didn't give a signal. The strategy is designed to wait for good opportunities.
- **BTC crashes 10% one day but the bot does nothing** — only EMA death cross triggers exit. No stoploss is intentional.
- **Single trade loses 5-10%** — within the distribution, CVaR 95% = −9.13%
- **A whole month with net loss** — normal; look at rolling 6-month/yearly
- **No entries at all when FnG > 80** — that's the rule; extreme greed phases are more prone to drawdown
- **Moves with BTC but smaller magnitude** — strategy is beta-biased, not an all-weather hedge

### ⚠️ These need attention (not necessarily immediate action)

| Observation | Reasonable explanation / action |
|------|-----------------|
| 5 consecutive losses | Within normal range (historical max 7 in a row); keep watching |
| DD 10-15% | Near PAUSE threshold; check `risk_monitor.py status`, don't intervene |
| A whole month with no trades | FnG has been > 80 for a long time, or ADX < 18. Check Fear & Greed and BTC trend |
| A position held > 10 days without movement | Very rare; check EMA values |
| Slippage > 0.1% (after live startup) | Order-book depth insufficient; consider reducing the pair count |

### 🚨 These are red lines (must investigate immediately)

| Observation | Action |
|------|-----|
| Telegram received a `RETIRED` alert | Strategy has auto-retired — **do not directly reset**; investigate the cause first |
| DD ≥ 15% and PAUSED | Wait for auto-resume (DD recovers to <10%); do not manually reset |
| Single trade loses >25% (beyond historical worst) | There's a black swan event; manually pause and check the market |
| 2+ consecutive months of walk-forward alerts | Edge is decaying; consider retiring |
| Bot process gone (`pgrep` returns nothing) | Check logs, restart the bot, check journald for crash reason |
| Live vs dry-run P&L gap >3%/month | Slippage/latency larger than expected; consider reducing size or switching strategy |

---

## 7. How to intervene (emergency handbook)

### Pause new entries (does not affect existing positions)

```bash
# Method 1: via risk manager (recommended, sends Telegram alert)
cd $PROJECT_DIR
python scripts/risk_monitor.py pause --note "your reason"

# Method 2: via Telegram command
# Send to the bot: /stopentry
```

### Full retirement (requires manual reset to recover)

```bash
python scripts/risk_monitor.py retire --note "your reason"
```

### Reset to ACTIVE (use with caution)

```bash
python scripts/risk_monitor.py reset --note "your reason"
```

### Stop the bot process

```bash
pkill -TERM -f "config_dryrun_honest15m"
# Wait 5-10 seconds for full shutdown
pgrep -af "config_dryrun_honest15m"  # confirm exit
```

### Restart the bot

```bash
cd $PROJECT_DIR
./scripts/start_honest_trend.sh dryrun
```

### Force-close a specific trade

```bash
# Send on Telegram: /forceexit <trade_id>
# Or curl the API:
curl -X POST http://127.0.0.1:8082/api/v1/forceexit \
  -H "Content-Type: application/json" \
  -d '{"tradeid": "1"}'
```

### View real-time logs

```bash
tail -f $PROJECT_DIR/logs/honest15m_dryrun_*.log
```

---

## 8. Transitioning from dry-run to live (roadmap)

**Don't rush to go live. Let dry-run run for at least 2-4 weeks to validate the following conditions**:

### Transition checklist

- [ ] Dry-run has accumulated ≥ **20 trades** (statistical significance)
- [ ] Rolling PF ≥ **1.2**
- [ ] Max DD < **12%**
- [ ] No RETIRED events
- [ ] No "live vs dry-run" deviation (dry-run can only be compared to backtest)
- [ ] Monthly walk-forward check has passed at least once with 4/4

### Transition steps

1. **Add Binance API key to SOPS** (see deployment doc)
2. Launch live: `./scripts/start_honest_trend.sh live`
3. **Keep dry-run running in parallel** — 15m dry-run as shadow validator to compare latency/slippage
4. Live first month: **only 1,000 USDT** (don't start with 10K)
5. Use risk_monitor monthly; gradually scale to 10K once stable

---

## 9. Common self-Q&A

**Q: Why no entries after a week?**
A: EMA 94/139 needs a very clear uptrend. Look at the BTC 15m chart — EMA 94 and 139 need to cross from below to above. If the market is ranging/falling, no entry. That's a feature, not a bug.

**Q: How to check the current FnG?**
A: Dashboard `http://localhost:3000` shows it in real time. Or `curl https://api.alternative.me/fng/?limit=1`. When current ≥ 80, the bot does not open any positions.

**Q: How big will the gap between dry-run and backtest be?**
A: Theoretically very small (both use the same market data). Significant differences only appear in live (real fill latency, order-book depth, fee tiering). Dry-run mainly validates strategy **logic bug-free**, not P&L accuracy.

**Q: When to start 1m live?**
A: Your call. Recommend starting after dry-run has run 2-4 weeks and confirmed stable. Command is ready: `./scripts/start_honest_trend.sh live` (prerequisite: SOPS has Binance key).

**Q: What if dry-run keeps losing money?**
A: Depends on the type of loss:
- **Single-month loss, 6-month PF still >1.2** → normal, no action.
- **6-month PF < 1.0, trades > 50** → do not launch live. Consider retiring or switching strategy.
- **DD > 15%** → risk_monitor auto-pauses; check state, do not manually reset.

**Q: Can I run multiple strategies in parallel?**
A: Yes. Currently 3 bots in parallel (15m spot 8082 / 1m MTF spot 8083 / 15m futures L+S 8084) + 2 daemons (event_reactor + event_dca_bot). Each bot has an independent port + independent SQLite DB. Telegram shares one chat (each bot distinguishes its own messages via bot_name).

**Q: Why ETH/BNB/SOL? Why not BTC?**
A: Phase A (2026-04-22) adopted: BTC uses DCA accumulation (weekly + event), not in the trend pool. Reason: BTC's return on trend strategy is below its own DCA baseline, and the user is long-term bullish on BTC (DCA accumulation fits better). ETH/BNB/SOL are high-beta alts and the trend strategy performs better there.

**Q: SOL was said to be unsuitable before — why add it back now?**
A: The previous conclusion was under the old framework (BTC-dominant). After Phase A switched to spot alts-only, re-running walk-forward: SOL as a high-beta alt captured more alpha (W4 2021 +143%). Also, futures L+S can hedge SOL's downside risk (W5 2022 LUNA: SOL spot lost 17%, futures L+S instead earned 48%).

---

## 10. Related file index

```
Main docs
├── docs/HONEST_TREND_REPORT.md     full technical analysis (why this strategy was chosen)
├── docs/DRYRUN_HANDBOOK.md         ← the one you're reading (daily ops)
├── risk_state.json                 current risk manager state (generated at runtime)
├── walk_forward_history/           monthly walk-forward archive

Active strategies
├── strategies/HonestTrendGeneric.py    base class (all HonestTrend* inherit)
├── strategies/HonestTrend15mDry.py     15m spot long-only (port 8082)
├── strategies/HonestTrend1mMTF.py      1m MTF spot long-only (port 8083)
├── strategies/HonestTrendFutures.py    15m futures L+S (port 8084, Phase B)
├── strategies/HonestTrend1mLive.py     1m live (old pair list, pending cut to A5)
├── strategies/dca_executor.py          DCA execution engine (shared by weekly/event)
├── strategies/event_dca_bot.py         event-driven DCA daemon (WebSocket)
├── strategies/risk_manager.py          state machine
├── strategies/telegram_alerts.py       alerts module

Config
├── configs/config_dryrun_honest15m.json           A5 spot long
├── configs/config_dryrun_honest1mmtf.json         A5 spot 1m MTF
├── configs/config_dryrun_honestfutures15m.json    Phase B futures L+S
├── configs/config_live_honest1m.json              old live (not cut to A5)
├── configs/backtest/config_backtest_15m_alts_a5.json     A5 backtest
├── configs/backtest/config_backtest_15m_futures_a5.json  Phase B backtest
├── configs/backtest/config_backtest_*.json        others

Scripts
├── scripts/start_honest_trend.sh       startup script
├── scripts/risk_monitor.py             monitor + CLI
├── scripts/walk_forward_check.py       monthly validation

Systemd timers (every 4h / monthly)
├── ~/.config/systemd/user/crypto-risk-monitor.{service,timer}
├── ~/.config/systemd/user/crypto-walkforward.{service,timer}

Archive (don't touch, and already .gitignored out of the public repo)
├── docs/RETIRED_STRATEGIES.md          retired strategies record (code deleted, only reasons + lessons remain)
```

---

## 11. Smart DCA dual-channel (BTC exclusive)

The trend strategy doesn't touch BTC; BTC is accumulated by this DCA combo:

### Weekly DCA (time-driven)
- Service: `crypto-dca.timer` → `dca_executor.py`
- Frequency: every Monday 00:00 SGT
- Amount: `$500 base × multiplier (0.0-3.0)`, weighted by FnG + cycle factors + KOL
- Status: dry-run (`DCA_LIVE_ENABLED` not set)
- Logs: `journalctl --user -u crypto-dca.service -f`

### Event-driven (WebSocket daemon)
- Service: `crypto-event-dca.service` → `event_dca_bot.py`
- Type: always-on, listens to Binance aggTrade WebSocket
- Triggers: 4-tier signals (FLASH 1m>3% / FAST 5m>5% / SUSTAIN 24h>10% / CAPITUL 30d DD>25%)
- Budget: $2000 reserve per month, $700/trigger (FnG<20 ×1.5, >60 ×0.7)
- Limits: 72h cooldown, max 3 per month
- State file: `event_dca_state.json`
- Self-test: `python strategies/event_dca_bot.py --self-test`

The two channels have **independent budgets** (not shared); both invoke `dca_executor.py` to execute. **To enable live**: add `DCA_LIVE_ENABLED=true` + Binance spot API key in SOPS `secrets.env`, and both channels go live simultaneously.

---

## 12. Core principles (one-liner edition)

1. **Dry-run to accumulate samples; don't rush to live**
2. **Daily glance Telegram, weekly check status, monthly check walk-forward**
3. **The rules are encoded; don't hand-tune**
4. **When red lines fire, trust the state machine — don't rush to reset**
5. **Monthly loss is normal; 6-month PF < 1.2 is the real alarm**

**Remember Taleb's words: strategies don't die slowly — they fail off a cliff.** Write the kill-switch ahead of time; when the cliff comes, the kill-switch saves you, not your judgment.

---

*Last updated: 2026-04-20. When something goes wrong, read this doc first, then the background in `HONEST_TREND_REPORT.md`.*
