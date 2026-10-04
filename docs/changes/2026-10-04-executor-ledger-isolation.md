# Executor ledger isolation and current-day DCA

Goal: keep Gate/HTX holdings separated by execution mode and execute DCA only from today's UTC rule.

Scope: filter all ledger reads and updates by environment; reject stale or future DCA rule dates; add focused decision tests and a disposable PostgreSQL ledger integration harness; synchronize the NUR deployment source.

Assumptions: retain existing trader/position identifiers and ledger schema. Switching mode starts from that mode's own holdings. Crypto remains dry-run/testnet. No strategy-rule or UI changes are needed. The user authorized commits, pushes and deployment on 2026-10-04.

Behavior:
- When dry-run and testnet positions share identifiers, reading, accumulating or closing one mode leaves the other unchanged.
- When the latest DCA rule is missing or dated before/after today UTC, no purchase occurs.
- When today's rule exists, buy its multiple once; later runs on the same day hold.

Acceptance:
- Executor and health-check plain-function harness: 28 tests passed.
- `CCXT_TEST_DSN='dbname=postgres host=/tmp/quant-executor-pg/socket port=55439' .venv-bots/bin/python tests/test_ccxt_executor_db.py`: passed against disposable PostgreSQL, covering isolated reads, DCA weighted average, mode-specific exits, realized PnL, re-entry and restart reads.
- Deployment copy matches the repository source (`cmp`).
- `git diff --check`: passed.

Limits: this change does not solve exchange-order reconciliation or partial-fill accounting. Deployment completed and verified on oracle-arm-002. The existing production database collation warning was observed but not changed.


## Deployment evidence (2026-10-04)

- Quant implementation pushed as `5d29062`; NUR deployment source pushed as `ac03c38`; dotfiles NUR lock pushed as `77e4fbf5`.
- Remote systemd-managed `nixos-rebuild switch --flake path:/var/tmp/quant-executor-isolation#oracle-arm-002 --impure` exited 0. Generation: `/nix/store/qlfm426cx2aq83r0q2h23qcl337rdf0c-nixos-system-oracle-arm-002-26.11.20261001.c59305b`.
- Installed executor SHA-256 matches the tested source: `e43b1961e154a5eb778d97bf9695150e5945509daeac52963f6788cf4f491bb0`.
- Executor is active, automatic restart count 0. Signal evaluator, dispatcher, all three Nautilus services and PostgREST are active; no failed system units.
- After restart and subsequent polling, each venue retains four trend rows and one DCA row, all `dry_run`; quantities unchanged from pre-deployment snapshot; duplicate open positions: 0. No new buy/sell or error messages after initialization.
- Rebuild log on arm-002: `/var/tmp/quant-executor-isolation.log`.
- Other sessions' local changes were preserved; NUR and dotfiles pushes used isolated worktrees.
