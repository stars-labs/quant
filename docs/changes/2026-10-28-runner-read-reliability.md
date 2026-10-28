# Owner runner request efficiency and read reliability

The runner previously fetched authenticated fees and free balances before
rejecting tiny allocations. It now checks available market minima first. A
quantity below the quantity minimum skips the ticker as well; a notional below
the minimum skips private requests after a fresh quote. Potentially tradeable
orders still query current fees and free balances, apply precision checks and
commit the intent before submission. Dust remains in the journal and in wallet
reconciliation.

Only the public signal-read RPC retries transient transport errors and HTTP
429/502/503/504 once after one second. Authentication, certificate and payload
errors propagate immediately. Freshness checks still follow successful reads.
No order submission or report-upload retry was added. Pause logs now identify
reconciliation, signal-feed or execution stages without signed exception text.

Validation on 2026-10-28:

- Runner suite: 146 tests run, 124 passed and 22 database-dependent tests skipped.
- New tests verify no private queries for untradeable allocations, live fee and
  wallet checks for potentially tradeable allocations, one retry for transient
  reads, bounded failure, and no retry for authentication/certificate/payload
  failures. Existing ambiguous-order recovery tests passed.
- Source commit: `7eeb3de`. Dotfiles deployment commit: `4da2fe90`.
- Final NixOS deployment exited 0 using nixpkgs revision `31ecbac`, matching the
  host's pre-change dependency revision. An initial deployment used an older
  local lock; the final deployment corrected that temporary version regression.
- Runtime SHA256 of exchange.py, reporting.py and cli.py matches the tested
  sources. At 10:05:04 UTC the private owner report was `healthy` with no pending
  orders. Telegram delivery state was healthy and acknowledged all 49 fills.
- Final system: `/nix/store/n52nk9c6dq64nsg2bva75hvk9rzcqn9y-nixos-system-oracle-arm-002-26.11.20261027.31ecbac`.
  Deployment log: `/var/tmp/quant-oct28-deploy-current.log` on Oracle.

No production fault or test order was injected. Long-term reduction in network
interruptions remains to be measured. Live strategy parameters, monthly funding
rules and the frozen prospective experiment were not changed.
