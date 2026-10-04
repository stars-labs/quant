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

Limits: this change does not solve exchange-order reconciliation or partial-fill accounting. Deployment verification is pending. The existing production database collation warning was observed but not changed.
