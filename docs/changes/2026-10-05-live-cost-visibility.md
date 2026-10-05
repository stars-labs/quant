# Live cost visibility and reproducible fee analysis

Scope: record gross executed quantity/cost and authenticated pre-order fee quotes;
show actual fees and unfilled active targets in the private HTX Telegram account;
add a read-only fee/slippage sensitivity CLI over the existing house signal record.
The trading rule, order budget, monthly funding and venue modes are unchanged.

Historical fee details must be verified against exchange matches and existing net
journal movements before being backfilled. Quotes absent from historical intents
stay unknown. Settlement/fee details/ledger remain one transaction. Telegram uses
the existing operator-private bot; no credentials are given to the dispatcher.
Rule sensitivity is explicitly13 independent equal-weight sleeves at Binance signal
prices, not a simulation of the funded100 USDT/20 USDT-cap executor or real HTX fills.

Acceptance: focused fee arithmetic, historical backfill, notification and analysis
tests; disposable PostgreSQL settlement rollback/idempotence and unchanged budgets;
read-only production analysis reproduces the existing0.1% rule view; initial six
fills backfill only after net reconciliation matches; remote NixOS switch completes;
private TG overview shows actual fees, services remain healthy, no validation orders.

Evidence will be appended after verification.

## Acceptance evidence

- **PASS — arithmetic/routing/analysis:** full plain-function harness168 tests passed
  across test_htx_fill_costs, test_trend_fee_analysis, test_htx_account,
  test_htx_notifications, test_htx_live, test_ccxt_executor, test_health_check,
  test_htx_preflight and test_alert_dispatcher. Final quantity formatting/position
  grouping was checked with20 fee/TG tests after that display-only change.
- **PASS — PostgreSQL:** disposable integration printed "Gross fill PostgreSQL checks
  passed: fee quote, atomic rollback, historical verification/idempotence" plus
  notification retry/restart deduplication and unchanged journal budget/fee/partial
  exit/replay/lock/month-rollover checks. Failed projection left gross fieldsNULL;
  adding/retrying historical metadata left net cash unchanged.
- **PASS — production schema/backfill:** migration041 applied. Initial six HTX fills
  verified against authenticated exchange matches; six gross details added. Installed
  backfill rerun added0 rows. Old pre-order fee quotes remainNULL, not reconstructed.
- **PASS — production reference:** installed analyze_trend_fees.py CLI returned21
  fee/slippage scenarios and "passed at published fee and zero slippage" calibration
  against strategy_record. Snapshot2026-10-05T15:59:59.999Z:185 entries,180 closed,
  five open. At0.20%/side the rule return was+34.018%, median asset+1.570%; adding
  five bp adverse slippage/side gave+32.204%, median+0.058%; ten bp gave+30.415%,
  median-1.432%. This is the rule reference, not the funded HTX account.
  Generated evidence is /tmp/quant-live-cost-evidence/rule-fees.json (not committed).
- **PASS — private TG:** delivery statehtx_menu_version=2 acknowledges the updated
  overview send. Installed account/trades rendering verifies all six historical fees
  at0.200%, aggregate fee0.2058 USDT at fill average prices; historical quote lines
  are omitted because unknown. Unfilled-target behavior is covered by the private
  account test; no artificial live signal was created for validation.
- **PASS — deployment/operation:** final NixOS rebuild ExecMainStatus=0; generation
  /nix/store/p5i5asbbvjfa5hq0y5n129b81xgmqn19-nixos-system-oracle-arm-002-26.11.20261003.a7868a7.
  Executor and dispatcher active, both NRestarts=0. HTX healthy=true/detail=ok at
  2026-10-05T16:12:38.936781Z. Six orders,zero pending,six gross-known; cumulative
  cash movement-102.9166359999998917 USDT, matching the pre-deployment journal.
  No validation order, funding entry or public strategy-stat write was made.

Initial implementation commits: quant59d18c6, nur22d3e03, dotfiles9fa3f020.
Final display commits: quant000f333, nur4381a68, dotfilesdb3ca6f0.
New real-order quote capture/settlement paths were tested offline and in disposable
PostgreSQL, not by forcing an extra production order. Runtime key arrangement and
existing unrelated PostgreSQL collation warning remain unchanged.
