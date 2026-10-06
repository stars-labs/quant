# Owner runner operational completeness

Goal: owners can understand execution, maintain funding, review actual performance and recover safely without developer intervention.

Scope and acceptance:

1. Read-only local diagnostics identify configuration, credential, journal, pending-order and heartbeat failures without printing secrets. Tests must cover diagnosis while the journal is locked by execution.
2. Consistent journal backup, checksum verification and recovery instructions. A WAL-mode running journal must retain committed funding and orders in the backup; corruption and overwrite must be rejected. Recovery must preserve account identity and never authorize a second executor.
3. Explain each cycle's trade and skip decisions in private reports, frontend and Telegram; distinguish feed failure, account mismatch, pending reconciliation, absent funding, minimum order and already-aligned targets.
4. Account-wide duplicate execution protection, including independent journal directories. Cross-host protection must preserve owner-operated execution and fail closed; it must not become hosted trading control.
5. Owner-confirmed deposits, withdrawals and allocation changes with auditable cash flows; no automatic calendar funding. Explain unused DCA allocation and maintain existing 100/100 monthly limits.
6. Historical equity, cash-flow-adjusted returns, actual fees and asset attribution; clearly timestamp and identify valuation prices. Verify small-account examples against journal movements.
7. Private Telegram reports for connected users through the existing single dispatcher, with ownership checks and delivery acknowledgements.
8. Owner setup and recovery guidance, including service placement on Oracle and private configuration. Validate the rendered account interface and deployment health.

Assumptions: existing personal HTX authorization and limits persist. No forced real test orders. Binance/Gate remain simulation, IB remains paper. Private financial artifacts and credentials never enter git. New arbitrary drawdown or liquidation thresholds require an explicit owner policy and are not silently imposed.

## Evidence and remaining work

Implementation in progress. The goal is not complete until all items above are implemented and verified. The initial increment introduces local doctor, consistent journal backup and checksum verification; production deployment and the remaining items are pending.

Initial validation: `python3 -m unittest discover -s runner/tests -v` ran 62 tests, passed with 14 PostgreSQL tests skipped because RUNNER_TEST_DSN was unset. WAL backup, checksum corruption, overwrite refusal, restored funding and locked-journal diagnosis were exercised.

The second increment records per-cycle local decisions, including feed failures even when no prices are available. Web and Telegram integration is still pending.

Decision report integration: migration 047 accepts only capped lists of normalized strategy/asset/reason fields. Private account UI renders English/Chinese explanations; operator Telegram adds the same reasons. Validation: 65 runner tests passed with RUNNER_TEST_DSN pointing to a newly created disposable starslab_runner_test database, including rejecting arbitrary reasons and credential fields. Svelte check: 0 errors, 12 existing warnings. Owner Telegram plain-function harness passed. Deployment and rendered UI verification remain pending.

Same-owner machine protection now claims a private account lock independently
of journal location and releases it with the journal. Tests cover duplicate
account refusal, different-account coexistence and restart after release.
67 runner tests passed with no skips. Cross-host locking remains incomplete.
Frontend logic tests: 14 passed. Prettier validation passed; final ESLint output
was still running at this observation.

Restore command implemented for an empty destination with matching configuration.
It requires explicit stopped-original confirmation, verifies backup checksum and
account identity, refuses existing journal/WAL/shared-memory/lock files, and does
not start execution. Restored funding is covered by a round-trip test. Runner:
68 tests passed, no skips. Full frontend lint completed with exit code 0.
Cross-host exclusion, exchange recovery exercise, equity history and cash-flow
workflow remain required; this increment is not overall completion.
