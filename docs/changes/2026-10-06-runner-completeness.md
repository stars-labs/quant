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

Cash-flow increment: owner-confirmed withdrawals and current-month allocation
transfers have durable reference IDs, reject conflicting repeats, negative
allocations, positive unconfirmed deposits and pending orders. Live confirmation
requires observed cash to match resulting journal cash and holdings to match the
journal; it never submits a transfer or order. Reports use net contributions so
withdrawals do not appear as losses. New deposits still use the existing monthly
fund command; profit withdrawals, incremental deposits and prior-month DCA
reclassification remain incomplete. Test coverage includes unchanged journal on
unverified live balance, idempotence, allocation conservation and pending refusal.

History increment: successful priced cycles persist private equity snapshots,
including observation time, oldest valuation-price time, fees and net contributions.
The history command reads while execution is active and returns latest observations
per UTC hour. No historical points are fabricated. Tests verify a withdrawal and
additional contribution leave investment PnL unchanged, latest hourly selection,
and refusal of stale/nonfinite valuations. Public report schema is unchanged in
this increment. Historical frontend integration and percentage return attribution
remain pending.

History validation: 76 runner tests passed, including the command reading snapshots
while another Journal instance holds the executor lock. Deployment remains pending.

History display integration adds migration 048 with capped private history points,
strict timestamp/amount fields and PnL arithmetic validation. Account UI displays
price and observation times, equity, net contributions and estimated PnL in the
selected language. 77 runner tests passed without skips; frontend check reports
0 errors / 12 existing warnings, full lint exit 0. Migrations 047/048 applied to
Oracle, and a private consistent pre-upgrade journal backup was created.

Incremental deposits now use unique references and gross monthly allocation caps,
including existing fund credits. Withdrawals do not reset caps. Live confirmations
check additional free spot cash, pending reconciliation and existing holdings.
This increment is not in the already-running Oracle deployment snapshot; it will
be included in the next owner-runner update. No live funding was added by development.

Deployment evidence: owner-operations-final completed ExecMainStatus=0, switching
to /nix/store/lrfrm7mvr2v5c75if7ckrcqyw016dz0l-nixos-system-oracle-arm-002-26.11.20261005.494ce7f.
Owner service active / NRestarts=0, log 2026-10-06T15:26:36Z healthy pending=0.
Private local report preserves 7 fills and includes 14 decisions / 1 history point.
Cloudflare deployment completed, version f5dcc291-1ce6-4cec-b91d-36e70ba43358.
Incremental-deposit tests: 78 passed, no skips. Rendered private-account browser
verification and remaining scope still pending.

Cross-month DCA: carry-dca explicitly moves a chosen unused prior-month allocation
to the current UTC month using an atomic paired debit/credit. Cash and contributions
stay constant; monthly deposit caps and daily sizing are unchanged. It refuses
invalid source months, excessive amounts and ambiguous orders. A repeated reference
is idempotent, while conflicting amounts are rejected. Live CLI reconciles and
checks the account without making a transfer or submitting an order. Production
funding was not changed during development.

Funding-tool deployment completed ExecMainStatus=0 and switched to
/nix/store/dg7qbfxanvwbvnk18xj67lx51harjhr4-nixos-system-oracle-arm-002-26.11.20261006.151fa4e.
Owner service active, NRestarts=0, 2026-10-06T15:32:29Z healthy pending=0.
Dotfiles funding-tools commit ba47e50a pushed.

Production account-page browser harness uses synthetic reports, a fake local token,
and mocked reads / aborted RPC writes. It verifies the rendered history, contribution
labels, execution reasons and viewport bounds in English desktop and Chinese mobile.
Both scenarios passed. It does not verify the Auth0 sign-in flow or actual owner data;
actual private report receipt was separately checked against production PostgreSQL.
Script: web/apps/app/scripts/check-account-display.mjs. Temporary screenshots:
/tmp/account-display-en.png and /tmp/account-display-zh.png.

Multi-user Telegram implementation: private /live and /trades use the requester's
bound chat projection; groups and mismatched senders cannot query reports.
Migration 049 renames the private projection and adds explicit opt-in alert
subscriptions. /livealerts on/off changes only notification delivery. Other users
have separate cursors, operator delivery is not duplicated, and explicit operator
opt-out is honored. Existing non-operator /me remains the public follow record.
Tests: 80 runner tests passed without skips; 11 account and 7 notification harness
tests passed. Production migration and dispatcher deployment are still pending.

Telegram deployment: migration 049 applied; NUR fdbc5c15, dotfiles 907024bf
pushed and Oracle switch completed ExecMainStatus=0. Current generation:
/nix/store/sd99lxhz0x3yz3afg9s69dhnsxd0nhqd-nixos-system-oracle-arm-002-26.11.20261006.151fa4e.
Dispatcher active / NRestarts=0. Production privileges: quant private-report EXECUTE
true; anon private-report EXECUTE false; authenticated alert-setting EXECUTE false.
Subscription count 0: no automatic enrollment of other users. Account command
harness now has 12 passing tests, including explicit on/off and group refusal.

Account page now provides a private Telegram binding card, preserving existing
research subscriptions and creating fresh private bindings with no research topics.
Site deployed version 724511fd-d2d1-4b30-bc10-e21f22ab4fbb. Updated synthetic browser
harness passes English desktop / Chinese mobile, including connected binding UI.
Frontend check 0 errors / 12 existing warnings; full lint and subsequent targeted
lint passed. Default account labels follow language until the user edits them.

An observed ConnectionResetError at 15:42:11Z paused execution safely; the next
cycle at 15:43:12Z recovered healthy, pending=0. A new un-deployed runner fix can
reuse the last dated valuation to publish paused status and normalized reasons
without refreshing its observed_at or fabricating price history. The existing
server freshness limits still apply. 81 runner tests passed without skips.

Cross-host protection: private configuration now pins live account operations to
the designated owner machine. Other computers use SSH to that owner and the same
journal, preventing separate copied journals from submitting live orders. The
owner SSH lock channel supports guarded remote recovery and answers nonce probes
without exchange keys, reporting tokens or trading calls. All copies must retain
the same owner designation; deliberate ownership migration requires stopping and
disabling the original service. No mechanism can prevent an owner from deliberately
creating independent configurations for the same exchange credentials.

84 runner tests passed, including lost-channel refusal and copied-configuration
order refusal. Actual game-box -> Oracle SSH probes passed competition refusal,
release/reacquisition, and refusal against the currently active real-account lock.
These probes did not call the trading API. Initial guard deployment completed
ExecMainStatus=0; a final owner-machine enforcement update is building in
owner-primary-execution.service, log /var/tmp/owner-primary-execution.log.

Final owner-policy deployment completed ExecMainStatus=0, generation
/nix/store/by1fhx1f2g80cp4scrpvki6vywg2x4q0-nixos-system-oracle-arm-002-26.11.20261006.151fa4e.
15:55:56Z live healthy pending=0. Live execution also requires the designated
OS user, so another local user cannot create an independent lock domain.
86 runner tests passed, including partial SSH responses timing out. Production
installed lock helper separately passed duplicate refusal and active-real-account
fencing. Running-owner backup verified integrity=ok, orders=7, funding=1.
Private probe configurations and the sandbox lock were removed; real-account
lock and private consistent backup were preserved.

Attribution implementation: realized and unrealized net PnL and actual fee totals
are grouped by strategy/asset, including closed positions. Net acquired quantity
and net sale proceeds account for base/quote fees without double subtraction.
Migration 050 validates bounded fields, unique asset/strategy groups, group math,
and reconciliation with total account PnL and fees. Account UI displays each group;
Telegram provides compact strategy summaries and caps long position/decision lists.
Tests cover partial sales, both fee currencies, closed positions without prices,
withdrawal-neutral PnL and rejected inconsistent uploads. 89 runner tests passed,
13 Telegram account tests passed; frontend check 0 errors / 12 existing warnings
and lint passed. Migration 050 applied to production. NUR c6195ae pushed; owner
service deployment is running in owner-pnl-attribution.service, log
/var/tmp/owner-pnl-attribution.log. Frontend deployment and rendered attribution
verification are pending at this observation.

Attribution deployment completed ExecMainStatus=0, generation
/nix/store/dgiq600fg6dzja2c5q8ks5zgypc8270a-nixos-system-oracle-arm-002-26.11.20261006.151fa4e.
Dotfiles 5890a24b pushed. Production private report healthy, attribution groups=6,
aggregate net PnL matches account PnL within 0.000001 USDT. Owner and dispatcher
active; 2026-10-06T16:09:25Z healthy pending=0. Website version
43e866ac-82af-4ba6-950c-9aeacc6abf50 deployed. Synthetic production browser harness
passed English desktop and Chinese mobile, now including attribution heading.
Percentage return measurement, full funding-flow display, user setup/upgrade and
package release verification remain pending; the overall objective is not complete.

Funding/return/delivery integration (2026-10-07): recent funding records include
locally confirmed deposits, withdrawals, budget transfers and paired DCA carry.
Unknown legacy confirmation times remain null; imports do not invent timestamps.
Private account UI includes mobile funding cards and states amounts in USDT.
Observed-period Modified Dietz estimates use timestamp-weighted local cash flows;
unknown opening legacy funding is permitted only when it reconciles to opening
net contributions. Timing/funding inconsistencies and nonpositive capital yield
unavailable reasons. No annualization, inception reconstruction or double fee charge.
Primary methodology reference: https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/.

Runner setup defaults to simulation and starts no funding, service or order.
Legacy owner upgrade requires explicit stopped/original-owner attestations and
preserves credentials, identity, budgets and ledger. Installers refuse active
services, foreground runners and held locks; modern CLI launchers share a global
installation lock to prevent startup during replacement. Restores accept inactive
installation lock files, refuse held locks, and initialize missing auxiliary tables.
Owner machine/user/state-directory pinning prevents copied-journal execution.
Realized-profit withdrawals may leave negative net contributions while cash stays
nonnegative; account and attribution PnL stay reconciled.

Validation: 123 runner tests passed without skips, sh -n installer passed; frontend
check 0 errors / 12 existing warnings, lint passed. Migrations 051–053 applied.
NUR 5a4e9a1 pushed, owner-runner-v020 deployment completed ExecMainStatus=0, generation
/nix/store/q13y1zsidhl2aaara0lcrg28pd07l0lj-nixos-system-oracle-arm-002-26.11.20261006.151fa4e.
Production private report healthy / funding_history count=1 / modified_dietz
percentage present. 16:58:20Z healthy pending=0; installed CLI version 0.2.0.
Website version 27ca3e03-3a44-4942-88d4-6d6093d03675 deployed; synthetic browser
harness passed English desktop and Chinese mobile with funding/return sections.
Built wheel matches every current Python source and contains license, no private
state. A staged wheel environment passed version, simulation setup and funding
history commands with no exchange calls. Public release download remains pending.
