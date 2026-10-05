# BearDawnVerse Quant

**English** · [中文](README.zh-CN.md)

> Open-source quant research, a private account dashboard, and **user-hosted HTX spot execution**. NautilusTrader powers the Binance research and IB paper engines.
> Built for research and learning — **not** a "get rich" button. All trading runs on **testnet / paper** by default.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org)
[![NautilusTrader 1.227](https://img.shields.io/badge/NautilusTrader-1.227-green.svg)](https://nautilustrader.io)
[![Dashboard](https://img.shields.io/badge/live-starslab.qzz.io-8a5cf6.svg)](https://starslab.qzz.io)

> **History:** this repo began as a freqtrade strategy collection. Freqtrade is removed; NautilusTrader powers Binance and IB, and the standalone ccxt runner handles user-hosted HTX execution.

---

## ⚠️ Disclaimer

- **For education and research only.** Trading carries high risk; you can lose your entire capital.
- All strategy parameters, backtests, and architecture reflect the author's personal risk appetite — not advice, and not necessarily suitable for you.
- **Do not run live without understanding the code.** The user-hosted HTX runner defaults to simulation and requires explicit local authorization for live spot orders. Binance research nodes stay on testnet and IB stays on paper.
- This is a tools / signals / dashboard project — never managed money or pooled funds.

---

## ✨ What's inside

- **User-hosted HTX execution** (`runner/`) — local exchange keys, SQLite recovery journal, confirmed monthly funding and actual fill fees. [Install and operate your runner](runner/README.md); [connect a private display](https://starslab.qzz.io/execution).
- **Crypto engine** (`nautilus_crypto/`, Binance testnet) — a smart-DCA **accumulator** (Fear & Greed–scaled buys), a **Donchian** trend follower, and a **signal layer** that pushes spike/dip Telegram alerts off mainnet public data.
- **US-equity engine** (`nautilus_equity/`, Interactive Brokers paper) — the **HonestTrend** EMA/ADX strategy live on an IB paper account (delayed market data), walk-forward validated.
- **Options research** (`nautilus_options/`) — Deribit cash-secured-put backtests (researched, not deployed).
- **Standalone bots & collectors** (`strategies/`) — Kelly sizing, risk manager (drawdown kill-switch), DCA executor, Deribit monitor, Telegram alert dispatcher, plus data collectors that feed the dashboard (market, curated global news, market-stress index).
- **Quant Lab** (`strategies/quant_lab.py`, `quant_models.py`) — dependency-light research models (BSM, cointegration, GARCH, HMM, Markowitz, PCA, …) runnable from the dashboard.
- **Live public dashboard** — [starslab.qzz.io](https://starslab.qzz.io): live execution, backtest playground, semiconductor supply-chain view, a 3D market globe, market-stress index, and a self-service backtest runner. SvelteKit on Cloudflare Workers, zh-default bilingual.

---

## 🏗️ Architecture

External market APIs are **never called from the browser/Cloudflare** (Binance blocks both Cloudflare egress and mainland-CN browsers). The data flow is three layers:

```
collectors (Python)            TimescaleDB @ oracle-arm-002          web (Cloudflare Workers)
strategies/*_collector.py  ──▶  quant.*  ──(PostgREST api.* views)──▶  SvelteKit reads api.panda.qzz.io
testnet research nodes        (+ Auth0 identity)                     starslab.qzz.io
user-owned HTX runner  ──upload-only display reports────────────────▶ private account displays
```

- **Live trading nodes** run as system services on **oracle-arm-002** (crypto: accumulator / trend / signal, all testnet) and on a local box (the US-equity IB-paper node + monitoring timers).
- **Data layer**: TimescaleDB (schema `quant`) exposed through **PostgREST** `api.*` views and bounded RPCs; **Auth0** provides identity. Private account reports use owner RLS and a separate upload-only token.
- **User exchange credentials** remain on the user's computer or server. The website has no exchange-key form or trading controls. Platform collector/database credentials use SOPS and are separate from the user-hosted runner.

---

## 📁 Project structure

```
runner/            User-hosted HTX runner, installer, local journal, tests and reporting
nautilus_crypto/    Crypto engine (Nautilus): accumulator.py, donchian.py, signal_*.py, live_*/run_* nodes
nautilus_equity/    US-equity engine via Interactive Brokers (own .venv with nautilus_trader[ib])
nautilus_options/   Deribit CSP backtests
strategies/         Standalone bots + collectors (kelly_sizer, deribit_monitor, health_check,
                    news_collector, stress_index, market_collector, quant_lab, …)
scripts/            Ops scripts (TimescaleDB sync, Binance data download, testnet USDT recycler, …)
migrations/         TimescaleDB schema (db `api`, schema `quant`) → PostgREST `api.*` views
web/apps/app/       SvelteKit dashboard (Cloudflare Workers) · web/apps/docs/ = Astro docs site
tests/              pytest-style tests (run via the venv directly)
```

Key docs: [`CLAUDE.md`](CLAUDE.md) / [`AGENTS.md`](AGENTS.md) (contributor & agent guide), [`STRATEGY_LEADERBOARD.md`](STRATEGY_LEADERBOARD.md) (strategy research log), [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

---

## 🚀 Quick start

Python uses local `uv` virtualenvs (no Makefile, no global pytest — invoke the venv interpreter directly):

```bash
# The nautilus venv (has nautilus_trader 1.227 + ib); used for crypto AND equity backtests
P=nautilus_equity/.venv/bin/python

# Run a crypto backtest
$P nautilus_crypto/run_accumulation.py        # or run_trend_crypto.py / run_portfolio_trend.py

# Run an equity backtest
$P nautilus_equity/run_honest_equity.py

# Refresh market data (ccxt → feather under user_data/data/)
$P nautilus_crypto/download_binance.py

# Run one test module (no pytest collector — drive the test_* funcs directly)
$P -c "import sys; sys.path.insert(0,'nautilus_crypto'); import test_signal_detect as t; \
  [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
```

Web dashboard (`cd web/apps/app`, [pnpm](https://pnpm.io)):

```bash
pnpm run dev       # local dev server
pnpm run check     # svelte-check typecheck
pnpm run lint      # prettier --check + eslint
pnpm run deploy    # vite build && wrangler deploy   (NOT `pnpm deploy`)
```

Secrets (sops + GPG):

```bash
sops -d secrets.env                              # view
sops exec-env secrets.env '<your command>'       # load into a command's env
```

---

## 🔐 Guardrails

- The user-hosted HTX runner defaults to **dry-run**; live orders require explicit local authorization and confirmed funding. Binance stays **testnet**; Interactive Brokers stays **paper**.
- Binance execution on Nautilus requires an **Ed25519** key; data-only mainnet nodes pass **no** key.
- Never commit plaintext secrets, virtualenvs, or generated data/catalogs/reports.

---

## 📜 License

[MIT](LICENSE). Provided as-is, with no warranty — see the disclaimer above.
