# Repository Guidelines

## Project Structure & Module Organization

This repository is a quant trading research and operations workspace centered on NautilusTrader. Core engines live in `nautilus_crypto/`, `nautilus_equity/`, and `nautilus_options/`. Shared standalone bots and helpers live in `strategies/`, while operational scripts live in `scripts/`. The public strategy track record (`/record`, Telegram topic `strategy_signals`) is computed from `quant.strategy_signals` via the `quant.strategy_record` view — see CLAUDE.md "Strategy track record"; `quant.nautilus_trades` is only the testnet execution ledger. Database changes are in `migrations/` for TimescaleDB/PostgREST and `supabase/` for Supabase schemas. Static dashboards are in `dashboard/`; the active SvelteKit/Cloudflare dashboard is in `web/apps/app/`, with docs in `web/apps/docs/`. Tests are in `tests/` and some module-local `test_*` files.

## Build, Test, and Development Commands

Python uses local virtualenvs instead of a Makefile. Prefer:

```bash
P=nautilus_equity/.venv/bin/python
$P nautilus_crypto/run_accumulation.py
$P nautilus_crypto/download_binance.py
```

`pytest` is not installed in the venvs. Plain `test_*` modules run with a small harness:

```bash
$P -c "import sys; sys.path.insert(0,'nautilus_crypto'); import test_signal_detect as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
```

Modules that `import pytest` (`tests/test_kelly_sizer.py`, `nautilus_crypto/test_crypto_accumulator.py`, `nautilus_equity/test_regime_gate.py`) need pytest layered on via uv:

```bash
uv run --no-project --python $P --with pytest -m pytest -q tests/test_kelly_sizer.py
```

For the web app:

```bash
cd web
pnpm run dev       # SvelteKit app
pnpm run build     # production build
pnpm --filter=@quant/app run check
pnpm --filter=@quant/app run lint
```

Use `pnpm run deploy`, not `pnpm deploy`.

## Coding Style & Naming Conventions

Python modules use snake_case filenames and functions, clear dataclasses where useful, and explicit imports. Keep strategy, data, and execution code separated by the existing directory boundaries. Svelte code follows the app-local Prettier, ESLint, TypeScript, and Svelte conventions; run `pnpm --filter=@quant/app run format` before broad UI edits. SQL migrations are numbered, for example `026_market_stress.sql`.

## Testing Guidelines

Add focused tests for sizing, signal logic, database parsing, and risk behavior when changing those areas. Name Python tests `test_*.py` and test functions `test_*`. For web changes, run `check` and `lint`; add component or route tests only where the app already has supporting infrastructure.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commits such as `feat(web): ...`, `fix(db): ...`, and `chore(ops): ...`. Keep subjects imperative and scoped when possible. PRs should describe behavior changes, list validation commands, link issues, and include screenshots for dashboard/UI changes. Note migration files, service changes, and deployment impact explicitly.

## Security & Configuration Tips

Never commit plaintext secrets, generated data, virtualenvs, catalogs, or reports. Treat `secrets.env` and `secrets.yaml` as SOPS-managed files. Keep trading guardrails intact: crypto execution remains testnet/dry-run unless explicitly authorized, and IB work stays on paper accounts.
