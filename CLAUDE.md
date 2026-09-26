# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## quant

Crypto + (planned) US-equity quant trading on **NautilusTrader**. Formerly `freqtrade-strategies`;
freqtrade is fully removed (single-stack migration done 2026-06-08). See `IMPLEMENTATION_PLAN.md`
for stage status and `STRATEGY_LEADERBOARD.md` for the strategy research log.

## Layout
- `nautilus_crypto/` — crypto engine (Nautilus). `accumulator.py` (FNG smart-DCA), `donchian.py`
  (trend), `signal_detect.py`/`signal_alerter.py`/`telegram_notifier.py` (signal layer),
  `trade_ledger.py` (writes `quant.nautilus_trades`), `live_*.py`/`run_*.py` (live nodes + backtests).
- `nautilus_equity/` — US-equity engine via IB (own `.venv`, has `nautilus_trader[ib]`). LIVE on
  IB paper via `quant-equity.service` (see Local services).
- `nautilus_options/` — Deribit CSP backtests (verdict: not deployed).
- `strategies/` — standalone bots/helpers (NOT freqtrade strategies anymore), ~30 modules:
  `telegram_alerts.py`, `kelly_sizer.py`, `risk_manager.py`, `dca_executor.py`, `deribit_monitor.py`,
  plus the collectors/evaluators the services run (`news_collector.py`, `stress_index.py`,
  `market_collector.py`, `alert_dispatcher.py`, `signal_evaluator.py`, `quant_lab.py`, …).
  `strategy_record.py` is the pure Donchian state machine behind the public track record (below).
- `scripts/` — `sync_local_state_to_timescale.py` (wf → TimescaleDB), `md_http_server.py`
  (localhost :3001 dashboard), `testnet_usdt_recycler.py`, misc backtest/sync/report helpers.
  (`download_binance.py` lives in `nautilus_crypto/`, not here.)
- `web/apps/app/` — SvelteKit dashboard on Cloudflare Workers (one route dir per page under
  `src/routes/`). Deploy: `pnpm run deploy` (NOT `pnpm deploy`). The `/nautilus` route shows live
  execution from `quant.nautilus_trades`. `web/apps/docs/` is the Astro docs site (built into
  `web/apps/app/static/docs/` — those generated files show as diffs, don't hand-edit them).
- `migrations/` — TimescaleDB schema, numbered `NNN_*.sql` (db `api`, schema `quant`, served via
  PostgREST `api.*`). `supabase/` holds two schema dumps for the separate Supabase project
  (auth + Realtime), not the trade DB.
- `systemd/` — source copies of the game-box user units (`quant-*.{service,timer}` incl.
  `quant-equity-watchdog.*`); the installed copies live in `~/.config/systemd/user/` — keep in sync.
  They hard-code the checkout path: moving the repo breaks every unit (203/EXEC) until the installed
  copies are re-pointed + `systemctl --user daemon-reload`.
- `docs/` — runbooks/checklists (`GO_LIVE_CHECKLIST.md`, `DRYRUN_HANDBOOK.md`,
  `RETIRED_STRATEGIES.md`) and `docs/research/` (AI-semis research data behind `/research`, `/semis`).
- Legacy, do-not-touch: `web-vanilla/`, `dashboard/`, `configs/`, `user_data/`, `freqaimodels/`,
  `tradesv3_*.sqlite`, root `start_*.sh` — freqtrade/pre-Nautilus era, kept for history only.
- `AGENTS.md` duplicates part of this file for other agents — update both when commands change.
- `flake.nix` + `.envrc` provide the direnv/Nix dev shell.

## venvs (uv; symlink to external python so they survive dir moves)
- `.venv-bots` — the standalone bots' interpreter (ccxt/websockets/psycopg2/pandas/requests). NO
  nautilus_trader.
- `nautilus_equity/.venv` — has nautilus_trader 1.227.0 (+ ib). Used to run crypto AND equity
  Nautilus backtests/tests (`sys.path.insert(0, <module dir>)` is how tests import siblings).
- pytest is NOT installed in either venv. Most tests are plain `test_*` funcs; three modules
  (`tests/test_kelly_sizer.py`, `nautilus_crypto/test_crypto_accumulator.py`,
  `nautilus_equity/test_regime_gate.py`) `import pytest` (fixtures/raises) and need the overlay below.

## Commands
Python (no Makefile/pytest — invoke the venv interpreter directly; `P=nautilus_equity/.venv/bin/python`):
- Run a Nautilus backtest: `$P nautilus_crypto/run_accumulation.py` (or `run_trend_crypto.py`,
  `run_portfolio_trend.py`; equity: `$P nautilus_equity/run_honest_equity.py`).
- Refresh market data: `$P nautilus_crypto/download_binance.py` (ccxt → feather under `user_data/data/`).
- Run one test module (no pytest collector — drive the `test_*` funcs with a one-liner):
  `$P -c "import sys; sys.path.insert(0,'nautilus_crypto'); import test_signal_detect as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"`
  (swap the dir/module to target another file; run a single test by naming just that one function).
- Modules that `import pytest` (or any test, by node id) — layer pytest on without installing it:
  `uv run --no-project --python $P --with pytest -m pytest -q tests/test_kelly_sizer.py`
  (append `::test_name` for one test). `tests/*` add `strategies/` to `sys.path` themselves; other
  tests sit next to their module (`nautilus_crypto/test_*.py`, `nautilus_equity/test_*.py`).
  Known pre-existing failure: `test_crypto_accumulator.py`'s module fixture errors with
  `ValueError: buffer source array is read-only` (6 errors; the rest pass).

Web dashboard (`cd web/apps/app`, pnpm):
- `pnpm run dev` — local dev server.   `pnpm run check` — svelte-check typecheck.
  (`dev`/`build` first run `scripts/sync-reports.mjs` — and `build` also `sync-starlight.mjs`,
  which copies the Astro docs build into `static/docs/`.)
- `pnpm run lint` — prettier --check + eslint.   `pnpm run format` — prettier --write.
- `pnpm run deploy` — `vite build && wrangler deploy` (NOT `pnpm deploy`, which is a different pnpm
  builtin). Deploys to the tron.network Cloudflare account, host `starslab.qzz.io` (migrated 2026-07).
- Svelte 5 runes (`$state`/`$derived`/`$props`); zh-default bilingual via `$lib/i18n` (`en.ts`/`zh.ts`).

## Web data flow (the load-bearing architecture)
**External market APIs are never called from the browser/Cloudflare — collectors write to
TimescaleDB and the web reads only our own APIs.** Binance blocks both Cloudflare egress AND
mainland browsers, so a SvelteKit `load` that hit Binance directly would fail in prod. Instead:
- Collectors (`strategies/*_collector.py`, `stress_index.py`, `scripts/`) fetch upstream data and
  `INSERT` into `quant.*` on TimescaleDB@oracle-arm-002.
- Each table is exposed as a read-only PostgREST `api.*` view (anon-selectable). The web reads them
  through the single `vps` client in `src/lib/api.ts`; backend URLs live in `src/lib/config.ts`
  (`API_BASE`=api.panda.qzz.io PostgREST, `AUTH_BASE`=gotrue, `SUPABASE_*`, `REALTIME_URL`=WS).
  The lone deliberate exception is the topbar BTC ticker, which calls Binance client-side only.
- **Adding a data-backed page** = migration (new `quant` table + `api` view) → collector or writer →
  a `vps.*` helper in `api.ts` + a `+page.server.ts` `load`. Apply a migration to prod with
  `ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/NNN.sql`
  then `psql … -c "NOTIFY pgrst, 'reload schema'"` so PostgREST picks up the new view.

## Strategy track record (the user-facing "wealth effect" loop)
Users follow **rule signals**, not our testnet fills. `quant.nautilus_trades` is the execution ledger and
is NOT a track record: node restarts re-open a position under the same `position_id` (TradeLedger now
closes the stale row as `exit_reason='superseded'`, no price/PnL).
- `signal_evaluator.py` `sweep_house` replays the house rule (Donchian 1h 168/72, same as
  `nautilus_crypto/donchian.py`; BTC/ETH/SOL) on closed Binance 1h bars every sweep → `quant.strategy_signals`
  (one row per trade, `live=false` = backfilled via `--backfill 2026-01-01`, never pushed) and
  `quant.strategy_assets` (last close + entry/exit trigger levels). Migration `032`.
- Views `quant.strategy_trades` / `quant.strategy_record` (+ `api.*`, anon) are the ONLY place stats are
  computed (net of 0.1%/side fees, vs buy-and-hold). Telegram, the daily report and `/record` all read them.
- `alert_dispatcher.py` pushes live entries/exits to topic `strategy_signals` + a Monday scorecard; topics
  are `strategy_signals` and `equity_trades` (`dca_events` is gone). Web: `/record`.

## Health checks (operator alerts)
`strategies/health_check.py` runs every 10 min in two roles that watch each other via
`quant.health_heartbeats` (migration 033): `--role server` on arm-002 (nur `quant-health-check` timer:
any failed system unit, required nautilus/quant units, stale `quant.*` tables, public API + `/record`,
desk heartbeat) and `--role desk` on the game box (`quant-health-check.timer`: failed/stopped `quant-*`
user units, a real IB API handshake, server heartbeat). Alerts go to the operator chat
(`TELEGRAM_CHAT_ID`) after 2 consecutive failing runs, recoveries once, reminders every 6 h. Add a
new service/table to its lists when you add one. `--dry-run` prints results and writes nothing.

## Deploy (oracle-arm-002, NixOS)
- Live crypto runs as **system services on oracle-arm-002**: `nautilus-accumulator`, `nautilus-trend`,
  `nautilus-signal` (all testnet/data-only). Packaged in `github:xiongchenyu6/nur-packages`
  (`modules/nautilus-*`, `pkgs/nautilus-trader`), wired in `dotfiles/nixos-configurations/oracle-arm-002/nautilus.nix`.
- Also on arm-002 (nur `modules/quant-collectors`, vendored copies of the `strategies/*.py` sources —
  keep both copies in sync when editing; `default.nix` copies an explicit file list, so a new module
  the evaluator/dispatcher imports — e.g. `strategy_record.py` — must be added there too): timers `quant-news-collector`, `quant-stress-index`,
  `quant-market-collector`; long-running `quant-signal-evaluator` + `quant-alert-dispatcher`
  (dispatcher = the ONLY Telegram getUpdates consumer — never start a second copy). market/signal/alert
  moved off the game box 2026-07-29; `findata.py` is vendored too (cache at
  `/var/lib/quant-collectors/findata-cache` via `FINDATA_CACHE_DIR`).
- `trade_ledger.py` is also vendored into nur `modules/nautilus-{trend,accumulator,equity-trend}/`.
- Module changes need: commit+push nur-packages (`git add` new files — flakes ignore untracked ones) → `nix flake update xiongchenyu6` in dotfiles →
  `NIXPKGS_ALLOW_INSECURE=1 nixos-rebuild switch --flake .#oracle-arm-002 --build-host root@oracle-arm-002 --target-host root@oracle-arm-002 --impure`.
- The nur overlay is NOT global on hosts → reference packages as
  `inputs.xiongchenyu6.packages.${system}.nautilus-trader`.
- Secrets: sops. Host secrets in `dotfiles/secrets/common.yaml` under `oracle-arm-002/*`
  (binance-api-key/secret, telegram-bot-token/chat-id, quant-password). Repo secrets in
  `secrets.env`/`secrets.yaml` (sops-encrypted; safe to commit). DB-touching services wrap the
  command in `sops exec-env secrets.env "<single quoted cmd>"` (quoting avoids a flag-eating bug).
- **Equity IB Gateway sidecar (oracle-amd-002, x86_64):** Gateway is x86-only + unpackaged in
  nixpkgs, so it runs as a `gnzsnz/ib-gateway` podman container (paper) on the AMD box, API bound
  to the wg mesh IP `172.22.240.97:4002` (wg0 is trusted; never public). The equity node connects
  over WireGuard (`IB_HOST=172.22.240.97 IB_PORT=4002`). Config:
  `dotfiles/nixos-configurations/oracle-amd-002/ib-gateway.nix`; runbook + 2FA/sops steps:
  `nautilus_equity/deploy/ib-gateway-headless.md`. Disable 2FA on the paper login first.
  Known failure: the nightly 23:59 auto-restart can stall at a "Gateway" dialog (LOGGED_OUT; port
  4002 refused inside the container, node logs "Failed to receive server version") — fix with
  `sudo systemctl restart podman-ib-gateway` on amd-002 (cold start does a full login, ~40 s).
- **Equity EXECUTION runs on the game box, NOT amd-002** (decided 2026-06-10). The amd-002 nix
  node `services.nautilus-equity-trend` traded but didn't persist (stale nur copy) + under-sized;
  it is **RETIRED** (`enable = false`). amd-002 hosts ONLY the IB Gateway now. The single equity
  node is `quant-equity.service` on the game box (see Local services). They must never both run —
  they share IB client id 8 on the one paper account.

## Local services (game box, `~/.config/systemd/user/quant-*`)
Monitoring/reporting on `.venv-bots`: `quant-ts-sync` (wf sync, reads local wf files), `quant-alerts`
(telegram reports), `quant-deribit`, `quant-risk-monitor`, `quant-daily-report`, `quant-dashboard`
(md_http :3001), `quant-account-snapshot` (needs the equity IB venv). The game-box copies of
`quant-market-collector`/`quant-signal-evaluator`/`quant-alert-dispatcher` are STOPPED+disabled
(moved to arm-002 2026-07-29 — do not re-enable, the dispatcher must stay single-instance),
`quant-testnet-recycler` (hourly `:50`) — keeps the arm-002 accumulator soak funded: the
one-directional smart-DCA drains testnet USDT → `-2010`, so `scripts/testnet_usdt_recycler.py`
sells a slice of the accumulated BTC back to USDT when buying power drops below the floor
(idempotent no-op otherwise; testnet has no faucet REST endpoint). Testnet key in
`~/.config/quant/backtest-runner.env` (`BINANCE_TESTNET_KEY`/`_SECRET_B64` = base64 of the Ed25519 PEM).
On `nautilus_equity/.venv` (needs nautilus_trader): `quant-backtest-runner` (playground compute)
and **`quant-equity`** — the US-equity LIVE node (`live_honest_equity.py`, IB paper, persists to
`quant.nautilus_trades` asset_class='equity' via in-node TradeLedger). Env in
`~/.config/quant/equity.env` (IB_* + EQ_QUOTE_PER_BASE_FX=0.74 for the SGD-base account + TIMESCALE_URL).
A **paper** IB account has no real-time US-equity data sub, so the node defaults to
`EQ_MARKET_DATA_TYPE=DELAYED_FROZEN` (free delayed feed); REALTIME just yields error 162 + zero bars.
The crypto bots `quant-event-dca`/`quant-reactor`/`quant-dca` were **retired** (moved to Nautilus@oracle-arm-002).

## Guardrails (hard)
- All crypto stays **testnet/dry-run**; IB stays **paper**. `DCA_LIVE_ENABLED` empty/false.
- Binance EXECUTION on Nautilus requires an **Ed25519** key (HMAC/RSA fail at session.logon).
- Data-only mainnet nodes must pass **no** Binance key (a placeholder → -2008 → 0 instruments).
- Never commit plaintext secrets, venvs, or generated data/catalogs/reports. Commit/push only when asked.
- Marketing = tools/signals/dashboard only — never 代客理财 / pooled funds.
- NixOS user services need `/run/current-system/sw/bin` on PATH (sops/pgrep/systemctl).
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
