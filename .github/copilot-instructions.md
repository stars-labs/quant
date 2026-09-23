# Copilot instructions for this repository

This repo is a quant trading and research workspace built around NautilusTrader, with a live public dashboard and operational collectors. Most of the repository’s guidance is duplicated in `README.md`, `AGENTS.md`, and `CLAUDE.md`; treat those as the project-level source of truth for operational details.

## Repository shape

- `nautilus_crypto/` — crypto engine built on NautilusTrader (accumulator, trend strategy, signal/alerting, live nodes, backtests)
- `nautilus_equity/` — US-equity engine via Interactive Brokers, using its own `.venv` with `nautilus_trader[ib]`
- `nautilus_options/` — research/backtests for Deribit options work
- `strategies/` — standalone automation and collectors (risk management, sizing, Telegram dispatch, market/news/stress-data collectors, quant lab models)
- `scripts/` — operational helpers such as Timescale sync, Binance data refresh, testnet USDT recycling, reporting helpers
- `migrations/` — numbered TimescaleDB/PostgREST schema migrations (`NNN_*.sql`)
- `web/apps/app/` — SvelteKit dashboard running on Cloudflare Workers; `web/apps/docs/` contains the Astro docs build that is copied into the app static output
- `tests/` — pytest-style tests, plus module-local `test_*.py` files next to relevant Python code
- `systemd/` — source copies of long-running service definitions; installed service copies live under `~/.config/systemd/user/`

## Build, test, and lint commands

Python workflows do not use a repo-wide Makefile. Use the project venv directly:

```bash
P=nautilus_equity/.venv/bin/python

# Run a crypto backtest
$P nautilus_crypto/run_accumulation.py
# or a trend/equity variant as needed
$P nautilus_crypto/run_trend_crypto.py
$P nautilus_equity/run_honest_equity.py

# Refresh market data (ccxt -> feather under user_data/data/)
$P nautilus_crypto/download_binance.py
```

Run a single Python test module directly, instead of invoking pytest collectors:

```bash
P=nautilus_equity/.venv/bin/python
$P -c "import sys; sys.path.insert(0,'nautilus_crypto'); import test_signal_detect as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
```

For tests under `tests/` that import from `strategies/`, use the same pattern:

```bash
P=nautilus_equity/.venv/bin/python
$P -c "import sys; sys.path.insert(0,'strategies'); import tests.test_kelly_sizer as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
```

Web dashboard commands (`cd web/apps/app`):

```bash
pnpm run dev
pnpm run check
pnpm run lint
pnpm run format
pnpm run deploy    # NOT pnpm deploy
```

## High-level architecture

This repository is structured around a three-layer data flow:

- Python collectors and live trading nodes fetch or compute market data and operational signals
- Data is persisted to TimescaleDB (`quant.*` schema) on `oracle-arm-002`
- The dashboard reads only the PostgREST `api.*` views exposed from that database, not upstream APIs directly

This matters because external market APIs are intentionally not called from the browser or Cloudflare Workers. Binance blocks Cloudflare egress and mainland-browser access, so the app reads from the project’s own API boundary instead of hitting upstream services client-side.

The operational pattern is:

```text
collectors / live nodes  ->  TimescaleDB  ->  PostgREST api.* views  ->  SvelteKit app
```

Supabase is used for auth and realtime, while the trade and market tables remain in the TimescaleDB/PostgREST stack.

For strategy work, the repo is organized by execution domain rather than a single service layer:

- `nautilus_crypto/` for crypto execution and signal logic
- `nautilus_equity/` for Interactive Brokers paper-account trading
- `strategies/` for standalone research helpers and operational bots
- `scripts/` for ETL and maintenance tasks
- `web/apps/app/` for dashboard presentation and operational readouts

## Key conventions and repository-specific patterns

- Python code uses local virtualenvs instead of a global environment or Makefile; the project expects direct invocation of the relevant `.venv` interpreter.
- Tests are pytest-style but are not run with the usual `pytest` collector in this repo; they are executed by directly invoking the module’s `test_*` functions.
- Imports between sibling modules rely on explicit `sys.path.insert(0, ...)` in tests and harnesses, rather than package install conventions.
- SQL migrations are numbered (`NNN_*.sql`) and are the mechanism for adding or changing database-backed views and tables.
- Keep data, strategy logic, and execution code near their domain directories rather than mixing them into a single app layer.
- Do not edit generated docs artifacts under `web/apps/app/static/docs/`; they are produced from the Astro docs build.
- `pnpm run deploy` is the release command for the dashboard; `pnpm deploy` is not the repo’s deploy flow.
- Svelte code in the dashboard follows the local app conventions and Svelte 5 patterns (`$state`, `$derived`, `$props`); the app is bilingual with a zh-default experience via `$lib/i18n`.
- Trade guardrails are explicit: crypto remains testnet/dry-run, and IB work remains on paper accounts unless an exception is explicitly documented.
- Secrets are handled with `sops`/GPG and must not be committed as plaintext; generated data, virtualenvs, and catalogs/report output are also not meant to be stored in the repo.
- The project carries a strong operational distinction between “research” work and “live system” work; service and deployment details are intentionally captured in docs and systemd configs rather than hidden in application code.

## Guardrails and operational expectations

- All crypto execution stays on testnet or dry-run; all IB execution stays on a paper account.
- Binance execution in Nautilus requires an Ed25519 key. Data-only mainnet nodes must not pass a live key.
- Never commit plaintext secrets, virtualenvs, or generated reports/catalogs.
- Keep deployment notes and service config in sync with the actual nodes and systemd definitions; the repo documents live host layouts and migration history for exactly this reason.

## Useful references in this repo

- `README.md` — project overview, quick start, architecture, and guardrails
- `CLAUDE.md` — repo layout, commands, deployment, and service topology
- `AGENTS.md` — agent-focused guidance that mirrors the key operational instructions
- `IMPLEMENTATION_PLAN.md` and `STRATEGY_LEADERBOARD.md` — current status and strategy research log
- `TUTORIAL_FOR_BEGINNERS.md` — educational onboarding for new contributors
