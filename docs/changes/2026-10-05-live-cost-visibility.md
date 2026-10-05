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
