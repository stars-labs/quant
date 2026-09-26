# Terminal State — single-stack NautilusTrader, retire freqtrade

**Decision (2026-06-07):** Consolidate onto **one engine: NautilusTrader**. freqtrade is
retired entirely. Driven by: (a) not wanting to maintain two stacks long-term, and
(b) freqtrade cannot trade US equities (CCXT-only), so the surviving single stack must be
the one that does both crypto and equities → Nautilus.

This is feasible because the **actual freqtrade footprint is thin** (recon 2026-06-07):
FreqAI unused (overfitting — dropped), hyperopt not a live dependency, pairlists is just
StaticPairList (BTC/ETH/BNB), no protections configured, the factor library is not imported
by any live strategy, and monitoring (telegram_alerts.py) + dashboard + TimescaleDB are
already custom and stack-agnostic.

## Terminal architecture
- **One engine (Nautilus)** runs all three: crypto accumulation, US-equity trend, and
  (later) crypto live execution.
- **Crypto = pure accumulation.** The fear-driven accumulator replaces the crypto trend
  strategies. `HonestTrend1mLive` (current crypto-trend live bot) is RETIRED with
  freqtrade, NOT ported — its trend edge moves to US equities. *(Confirm this assumption.)*
- **US equities = trend.** HonestTrend ported to event-driven (done).
- **Hyperopt** = Optuna/vectorbt wrapping Nautilus `BacktestNode`. Built only when
  optimizing; never a runtime dependency.
- **FreqAI = dropped.** Not migrated.

## Keep (stack-agnostic, untouched)
`strategies/telegram_alerts.py`, the Svelte dashboard, TimescaleDB, `strategies/kelly_sizer.py`,
the standalone Event/Smart DCA daemon (0 freqtrade imports — independent until folded in).

## Retire / archive
The `freqtrade` package + all `configs/config_*.json`, the crypto-trend strategies
(`HonestTrend*` except as reference), the unused factor library and `freqaimodels/`
(archive, don't migrate).

---

## Stage 1 — Nautilus engine foundation — DONE
Equity trend port (`nautilus_equity/honest_trend_equity.py`) + crypto accumulator
(`nautilus_crypto/accumulator.py`). kelly_sizer reused. Exchange-side stops, RTH gate,
VIX regime gate (real VIX 2011-2026). 48 tests green. Crypto accumulator validated on real
Binance data through the 2026-06 dip (smart DCA: -9.56% cost basis, +44 pts ROI vs naive).

## Stage 2 — Equity real data + validation — IB paper account READY 2026-06-09
Paper account live (user `xiongchenyu6`). Headless Gateway path chosen: **x86_64 sidecar**
on `oracle-amd-002` (aarch64 oracle-arm-002 can't run the x86 Java Gateway), as a
`gnzsnz/ib-gateway` podman container, API on wg mesh `172.22.240.97:4002`. Config in
`dotfiles/.../oracle-amd-002/ib-gateway.nix`; runbook `nautilus_equity/deploy/ib-gateway-headless.md`.
`download_ib.py` now defaults to port 4002 (Gateway paper).
TODO: (1) disable 2FA on paper login, add creds to sops, `nixos-rebuild` amd-002; (2) run
`download_ib.py` for NVDA/AMD/QQQ adjusted bars → ParquetDataCatalog; (3) feed real KellyStats;
(4) validate ADX/indicators vs talib; (5) NVDA 2024 10:1 split data-integrity check.

## Stage 3 — Persistence + dashboard unification
Write Nautilus fills/positions to TimescaleDB via `on_order_filled`/`on_position_closed`;
add `asset_class` ('crypto'|'equity') dimension; dashboard shows both side by side.
Do this with REAL data only (don't pollute prod DB with synthetic trades).

**Crypto half: DONE** — `trade_ledger.py` writes Accumulator/Donchian round-trips to
`quant.nautilus_trades` (asset_class defaults 'crypto').
**Equity half: DONE & LIVE 2026-06-10** — `HonestTrendEquity` hooks
`on_position_opened/changed/closed` → `TradeLedger(asset_class="equity")`. Migration
`013_nautilus_trades_asset_class.sql` APPLIED (column + `api.nautilus_trades` view). The
equity node now runs as **`quant-equity.service` on the GAME BOX** (not amd-002) — the
amd-002 nix node `nautilus-equity-trend` traded but never persisted (stale nur copy) +
under-sized, so it was stopped; amd-002 = IB Gateway only. The game-box node connects to the
Gateway over wg (172.22.240.97:4002, client id 8) and persists in-process. Sizing fix: IB
margin account reports `base_currency=None` → `balance_total()` no-arg RAISES → `_equity_usd`
reads `balances_total()` × `EQ_QUOTE_PER_BASE_FX=0.74`. Migration 016 APPLIED (DELETE grant).
REMAINING: set `services.nautilus-equity-trend.enable=false` in dotfiles (amd-002) before its
next rebuild; verify the first live round-trip persists when US market opens.

## Stage 4 — Crypto live execution on Nautilus — DEPLOYED TO PROD (testnet) 2026-06-07
Packaged nautilus-trader (aarch64 wheel) + a nautilus-accumulator NixOS service in
nur-packages; deployed to **oracle-arm-002** via dotfiles + nixos-rebuild switch. The box
also got bumped 26.05→26.11 (fixed a stale supabase-realtime mix-deps FOD hash that blocked
it). Live on Binance **testnet**: service active, Ed25519 session.logon authenticated,
1372 instruments, stream connected; buys on hourly bar close. Dashboard/API survived
(api.panda + quant both 200). Soak running. Flip `testnet=false` only after weeks clean.

### (prior) testnet PROVEN locally 2026-06-07
`TradingNode` + native Binance adapter running the accumulator (`live_accumulation.py`).
END-TO-END VALIDATED on Binance testnet: connect → Ed25519 `session.logon` → load account
(testnet balances) + 1372 instruments → subscribe 1m bars → on first bar (FNG=12 extreme
fear → deep-fear 6× boost) the accumulator placed a live order: BUY MARKET 0.0096 BTC
@ $62,515.86, Submitted → Accepted (venue_order_id) → Filled. The smart fear logic fired
in a real exchange environment. KEY GOTCHA: execution requires an **Ed25519** API key
(HMAC/RSA deprecated — they authenticate + load account but fail at session.logon).
REMAINING before real money: long unattended dry-run/testnet soak (reconnect, order
timeout, reconciliation, daily restart), fold in the DCA daemon, then mainnet with
`DCA_LIVE_ENABLED=false` lifted only after weeks of clean operation.

## Stage 5 — Equity live (IB paper → real)
`TradingNode` against IB paper, semiconductor pool, full sessions unattended; reconcile
Cache vs DB. Promote to real only after sustained clean paper operation.

## Stage 6 — Hyperopt via Optuna (build when needed)
Optuna study wrapping a Nautilus `BacktestNode` run; objective = Calmar/Sharpe with DD
penalty (mirror the old HonestHyperOptLoss). Not a blocker for going live.

## Stage 7 — Decommission freqtrade — CORE DONE (PATH A executed 2026-06-08)
**Done:** freqtrade core repo deleted (~11G freed); daemons repointed to `.venv-bots`;
`download-data` replaced by `nautilus_crypto/download_binance.py` (ccxt); repo renamed
`freqtrade-strategies`→`quant`, services `crypto-*`→`quant-*`. Dead freqtrade strategies/
scripts/news-cluster git-rm'd. Stale freqtrade refs scrubbed from kept live code
(telegram_alerts health-check + daily-report P&L → `quant.nautilus_trades`; ts-sync dead
sqlite stage removed).

## Stage 8 — True single-stack crypto: port signal layer onto Nautilus, retire daemons
**Why:** the only remaining parallelism — `quant-event-dca` (dry-run dip/FNG) + `quant-reactor`
(spike) are the *signal/alert layer* (Telegram + dashboard feed); Nautilus is *execution* (no
alerting). Decision 2026-06-08: **port alerts into Nautilus, then retire the daemons** (single
process). Key constraint: signal detection needs REAL (mainnet) public prices even while
execution stays testnet → the alerter runs on a mainnet **data-only** feed.

**Goal**: Nautilus emits the spike (PUMP/DUMP) + accumulation-dip (FLASH/FAST) Telegram alerts;
then stop event-dca/reactor/dca.
**P1 (code+test, no deploy)** — `telegram_notifier.py` (sink), `signal_detect.py` (pure
Spike/Dip detectors ported from the daemons), `signal_alerter.py` (Nautilus Actor wiring
bars→detectors→notifier) + tests.  **Status: COMPLETE 2026-06-08** — 9 pure unit tests pass;
integration test drives the actor through a real BacktestEngine (synthetic spike+dip path) and
confirms both Telegram alerts fire via the subscribe→on_bar wiring. Fixed a latent cooldown bug
(epoch-0 init suppressed the first alert) the original daemons had.
**P2 (deploy)** — data-only mainnet signal node + nur module; deploy to oracle-arm-002.
**Status: DEPLOYED 2026-06-08** — `run_signal_alerter.py` (data-only, no exec client, no keys →
loads 3591 instruments anonymously via public exchangeInfo; first attempts failed on a
placeholder key that forced an authed fee-tier call). `nautilus-signal` nur module + dotfiles
`services.nautilus-signal` (BTC/ETH/SOL, 1-min, mainnet). Telegram creds added to host sops
(`oracle-arm-002/telegram-{bot-token,chat-id}`, same bot/chat as legacy daemons). Service
`active`, SignalAlerter RUNNING, startup heartbeat sent (no telegram errors). **Remaining: soak
+ confirm a real spike/dip alert lands before P3.**
**P3 (retire)** — **DONE 2026-06-08**: stopped+disabled `quant-event-dca`/`quant-reactor`/
`quant-dca.timer`; trimmed ts-sync to the `wf` stage only (event_dca state frozen; historical
event_dca_triggers rows remain in the DB for the dashboard). Crypto is now single-stack: all
execution + signal runs on Nautilus@oracle-arm-002 (accumulator + trend + signal). Kept on the
game box: ts-sync(wf), alerts, deribit, risk-monitor, daily-report (monitoring/reporting only).
**Cleanup done 2026-06-08**: `/quant` CLAUDE.md written; daily-report Nautilus P&L wired up
(`quant-alerts` now runs via `start_telegram_alerts.sh` → `sops exec-env secrets.env`, restoring
the TIMESCALE_URL the rename dropped); local health watchdog disabled (`HEALTH_CHECK_SERVICES=`,
default now empty) so it stops false-alarming on the retired event-dca/reactor.
**Still open**: `md_http_server` :3001 (localhost-only, freqtrade-free, no consumers — user to
decide retire vs keep as a local view); dashboard event_dca_triggers panel is historical-only
(live execution = /nautilus route).

**STAGE 8 COMPLETE** — crypto runs on one stack (NautilusTrader); the freqtrade-era parallel
daemons are gone.

---

## Joint Kelly (deferred but flagged)
Semis are highly correlated with each other and with BTC. Replace scalar Half-Kelly with
the covariance form f* = Σ⁻¹μ across the pool once Stages 2-3 are stable.

## Hard guardrails
- Everything paper/dry-run/testnet first; real money only after sustained clean operation.
- `DCA_LIVE_ENABLED=false` until crypto live on Nautilus is proven.
- Secrets stay sops-encrypted (already verified: secrets.env/secrets.yaml are sops, safe).
- Never commit plaintext secrets, venvs, or generated data/catalogs.

---

## Stage 9 — Dashboard redesign: honest, crypto + US-equities (2026-06-08)
**Why:** the homepage is branded "Crypto Quant" and its KPI wall (+954%/Calmar 430/Sharpe 2.46,
12,341 trades, "8 策略/30 回测") is aggregated over `quant.backtest_runs` — the now-**deleted**
freqtrade strategies. The "真金白银" claim sits on retired strategies + testnet. No equities, and
the actual live engine (`/nautilus`) isn't in the nav.

**User decisions (2026-06-08):** (1) equities = show **backtest results, clearly labeled** (not live
yet); (2) replace misleading numbers with **honest current numbers**; (3) don't delete the analytical
panels (WF/strategies/archive/factors) — **regenerate them with Nautilus** instead of freqtrade.

**Data architecture:** isolate Nautilus backtest stats in their own table/views (mirrors how
`009_nautilus_trades` isolated live exec from freqtrade `trades`) — do NOT mutate `backtest_runs`.

- **R1 — Nautilus backtest→stats pipeline (crypto)**: migration `quant.nautilus_backtests`
  (+ `api.nautilus_backtests` list + `api.nautilus_stats` aggregate views, anon-granted). Harness
  runs the deployed crypto strategies (Donchian per-asset + portfolio, accumulator) on real Binance
  data, collects profit/Sharpe/Sortino/maxDD(EquityRecorder)/Calmar/win-rate/trades, loads rows
  tagged engine='nautilus', asset_class='crypto', kind='backtest'. **Status: DONE 2026-06-08.**
  `010_nautilus_backtests.sql` applied; `nautilus_crypto/backtest_stats.py` loaded 3 validated rows
  (Donchian full +160%/Sharpe 3.64, recent-OOS +22.6%/Sharpe 2.20, BTC smart-DCA +376% ROI). Served
  via `api.nautilus_stats`/`api.nautilus_backtests` (anon; PostgREST schema reloaded). Gotchas:
  EquityRecorder is 1h-hardcoded (1d accumulator uses its own ROI); accumulator needs a big starting
  balance or it hits a cash wall and truncates.
- **R2 — Equity backtests**: run HonestTrend on the semiconductor pool → same schema,
  asset_class='equity', clearly labeled backtest. Load.
- **R3 — Frontend rebrand + honest homepage**: BearDawnVerse positioning = crypto + US equities;
  new hero copy (drop BNB/futures overclaim; honest "live testnet + backtest" framing); promote
  `/nautilus` (live exec) into nav; KPIs from `api.nautilus_stats`; two-asset structure.
- **R4 — Regenerate analytical pages with Nautilus**: WF (Nautilus walk-forward), strategies
  (current Nautilus strategies + their real params/results), archive (Nautilus runs); factors/hyperopt
  → honest current state (repoint or "建设中" rather than fake freqtrade content).

## Stage 10 — Strategy signals + public track record (the "wealth effect" loop, 2026-09-26)
**Goal**: users get the house trend rule's buy/sell calls in Telegram and can see its honest record.
Feedback: "Telegram data is meaningless, no buy/sell points, the bull came and we made nothing" — the
Donchian 1h rule caught the Aug-18/19 rally (+21–30%) but nothing pushed it (dca_events dead since 06-07).
**Success Criteria**: backfill replay == reference (38 closed, 37% win, +~5% vs hold −~5% YTD, net of fees);
live entry/exit pushed exactly once; Monday scorecard; `/record` page; daily report reads the same view.
**Tests**: tests/test_strategy_record.py, tests/test_house_sweep.py, tests/test_alert_dispatcher.py,
nautilus_crypto/test_trade_ledger.py; local PG+PostgREST integration (32 checks); svelte-check/build.
**Status**: Implemented + verified locally. Deploy pending: migration 032 → `--backfill 2026-01-01` on
prod → nur (quant-collectors + nautilus-* trade_ledger) → nixos-rebuild arm-002 → `pnpm run deploy`.
