# Wallet dust reconciliation

After a large token holding was sold, subtracting the filled sell quantity
from the original holding left a small floating-point cancellation error.
Comparing only at the scale of the remaining dust incorrectly paused execution.

Wallet checks now allow four floating-point representable steps at the original
holding scale per journal position. Real quantity differences and untracked
assets still pause execution; no journal quantities or exchange balances are
changed to make the check pass.

Validation: the runner suite ran 141 tests successfully, with 22 database-dependent
tests skipped. New regressions cover the observed cancellation error, a larger
discrepancy that must still pause, and an untracked asset. Read-only HTX order and
fill checks matched the journal quantities and net cash.

Oracle NixOS deployment completed successfully on 2026-10-07. At 13:20:34 UTC,
the owner runner logged `htx/live healthy, pending=0`; the private uploaded report
and Telegram dispatcher's acknowledged health state also returned to `healthy`.
Deployment log: `/var/tmp/runner-dust-fix.log` on oracle-arm-002.
