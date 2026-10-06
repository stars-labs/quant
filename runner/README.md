# Starslab runner

Open-source HTX spot execution on **your computer or server**. Exchange keys,
monthly funding, order submission and the SQLite journal stay on your machine.
Starslab receives private display reports through an upload-only token. It cannot
start, stop or change your trading settings through that token.

The runner defaults to simulation. Binance research and Interactive Brokers paper
nodes are separate. Gate live trading is not supported by this runner yet.

## Install

Linux and macOS are supported; Windows users can use WSL2. Install the tagged
release with one command:

```sh
curl -fsSL https://raw.githubusercontent.com/stars-labs/quant/runner-v0.1.1/runner/install.sh | sh
```

The installer uses [uv](https://docs.astral.sh/uv/guides/tools/) and Python 3.13 in
an isolated tool environment. It checks the executable and repairs its installation
when rerun. It preserves local files, requires a running service to be stopped
before upgrading, and does not start a service or grant live permission.

To install from a source checkout instead:

```sh
uv tool install --python 3.13 ./runner
starslab-runner init
```

## Try simulation

```sh
starslab-runner fund
starslab-runner run --once
starslab-runner status
```

Simulation uses public HTX spot prices and a conservative 0.2% fee per side. It
never calls an exchange order endpoint. Funding defaults to 100 USDT trend and
100 USDT BTC DCA for the current UTC month. These are simulated credits in this
mode. Review the results before choosing live execution.

## Connect your display

1. Sign in at [Your accounts](https://starslab.qzz.io/execution).
2. Create an HTX display connection. Choose Simulation or Live spot to match your
   local runner. The choice is display metadata and does not authorize trading.
3. Save `display.json`, then attach it locally:

```sh
starslab-runner connect-display ~/Downloads/display.json
```

The file contains an upload-only reporting token. Its hash is stored on the
platform; the token is returned once and cannot be retrieved later. Revoking it
stops uploads, **not trading**. Reports are visible only to your signed-in account.
Starslab displays user-reported data, not independently verified exchange records.

## Enable HTX live locally

Use a dedicated spot account or subaccount with no existing holdings. Create an
API key with Read and Trade permissions, without withdrawal permission. Restrict
its IP to your runner's public egress IP. Keep the key out of chat, Git and display
configuration files.

Stop any existing executor using that same account before proceeding. One exchange
account must have exactly one runner. Separate installations cannot coordinate
with each other through the display service.

```sh
starslab-runner configure-live
```

This command reads keys through hidden local prompts, verifies the UID and spot
account, and requires typing `ENABLE LIVE` locally. Keys are written to the local
credentials file with mode 0600. No order is placed by configuration. A separate
live journal prevents simulation history from becoming real holdings.

Deposit USDT into the verified spot wallet and confirm the current month's new
funding locally. The runner verifies that the additional cash exists:

```sh
starslab-runner fund
starslab-runner run --once
starslab-runner run
```

The first `run` may submit real market orders for current active research signals
and today's DCA allocation. It does not replay past DCA days. A funding command
does not move money. The same month cannot be credited twice or silently changed.
Trend sale proceeds remain reusable; unused DCA funding is not carried into next
month's DCA allowance. Confirm each new month's deposit with `fund` while the
executor is stopped.

## Local settings and operation

Files default to `~/.config/starslab-runner/`. Use `--home /private/path` before the
command to choose another location. `config.json` contains local strategy settings,
not exchange keys. Default trend orders are capped at 20 USDT. Modify allocations,
asset selection, new trend entries or DCA while the runner is stopped; changes
take effect on restart. Existing trend positions still receive exits when new
trend entries are disabled. DCA BTC is never sold by the trend rule.

If your key is restricted to an egress IP on another server you own, set the local
`proxy_url` to your own HTTP CONNECT or SOCKS proxy (for example
`socks5h://127.0.0.1:11080`). Exchange HTTPS remains encrypted through that tunnel;
the runner retains the keys locally. Never route a trading key through an untrusted
proxy. PySocks is bundled for SOCKS transport.

Run in a terminal with `starslab-runner run`, or install the supplied systemd user
unit with the correct executable and home paths for your machine. Enable user
lingering if you want it to survive logout. On macOS, use your own launchd job or
terminal session. Stop your local process or service to stop execution; the web
display has no trading controls. Stopping does not sell holdings.

Back up the entire private directory, including the SQLite journal. Do not delete
the journal to resolve a pause: this destroys the original client order IDs needed
to recover ambiguous submissions. Never start a fresh journal on a funded account
with existing positions. Existing bot migrations require an accounting import and
balance reconciliation before live execution.

The journal records intentions before exchange calls. A timeout or unknown order
remains pending and blocks new orders. Restart recovers using the original client
ID. It never resubmits an uncertain order. It checks all spot holdings against the
journal and pauses on untracked transfers or trades. Unsupported third-currency
fee deductions (HT/points) pause accounting; use base/USDT fee settlement.

Actual fees are taken from final match records. Authenticated symbol-specific
effective and basic taker rates are recorded before each live order; they may
differ from the charged fee. A 0.3% ceiling reserves headroom. Exceeding it pauses
execution, rather than inventing a fee or writing an inconsistent ledger.

Signals are validated against a single server snapshot, with a 2-minute feed-age
limit and a 3-hour market-data limit. Missing or stale signals cannot trigger sales.
Account valuation uses the public hourly research closes and can differ from the
exchange's current mark. Report uploads failing or being revoked do not stop
otherwise healthy local execution. A signal-feed outage prevents new signal-based
orders, while previously submitted orders are still reconciled.

## Develop and verify

The runner is covered by the repository's [MIT license](../LICENSE).

```sh
python -m unittest discover -s runner/tests -v
```

Migration integration tests additionally require psycopg2 and `RUNNER_TEST_DSN`
pointing to an empty disposable database named `starslab_runner_test`. They create
and remove fixture schemas and refuse any other database name. Tests exercise
timeout recovery, duplicate signals, strategy isolation, fee reconciliation,
anonymous upload permissions and cross-user display privacy.

### Diagnose and back up

`starslab-runner doctor` performs offline checks of private settings, account-bound
journal integrity, pending intents and the latest heartbeat. It never submits an
order or changes the journal. An attention result includes a recovery action;
a stale report alone does not prove the service stopped.

`starslab-runner backup /private/path/journal.sqlite` creates a consistent SQLite
snapshot, including committed WAL changes, and a `.sha256` checksum. Both files
are private. The command refuses to overwrite an existing backup. Validate with
`starslab-runner verify-backup /private/path/journal.sqlite`.

Back up configuration and credentials separately in private encrypted storage.
To recover, first stop the original owner service and confirm that no executor
for that account is running on another host. Verify the backup, restore it into
the original private state directory with permission 600, and restore its matching
configuration. Never replace a journal while its service is running. Run `doctor`
before restarting; pending intents must be reconciled with existing HTX client
IDs, never deleted or submitted again. A backup restores historical state; HTX
may contain later fills, so reconcile against the exchange before resuming.

`starslab-runner decisions` shows the last execution cycle's local decisions,
with an observation timestamp. Reasons distinguish absent entry signals, targets
already processed, disabled entries, unavailable confirmed budget, orders below
exchange minimums, submitted entries/exits, and pending reconciliation. Feed or
execution failures record only the failing stage and exception class; signed
exchange URLs and credentials are never included. This local decision snapshot
is written even when price fetching fails. Normalized reasons are included in private web reports and the owner Telegram account view. Deploy migration 047 before updating a live runner.

Live execution also holds an account lock under the OS user's private state
folder, independent of `--home` and journal location. A second process for the
same HTX account under that OS user fails before exchange access. Private
configuration identifies the designated owner machine. Live account operations
and execution must run as the designated OS user on that machine; use SSH from another computer to operate
the same owner journal. Copied configurations cannot directly trade elsewhere.
Recovery from another machine verifies the owner account lock through an SSH
channel before touching the destination journal. All copies for an account must
retain the same owner designation. Stop and disable the original service before
explicitly moving ownership to a new machine.

For an empty destination with the original matching private configuration,
`starslab-runner restore /private/path/journal.sqlite --confirm-original-stopped`
verifies the checksum, SQLite integrity and account identity, then restores the
journal without starting a service or submitting orders. It refuses any existing
journal, WAL, shared-memory or lock file. The confirmation asserts that you have
stopped the original executor on every host; the current machine's account lock
also blocks a concurrently running local live executor. Resume only after checking
for fills newer than the backup. Configuration, credentials and upload tokens
are deliberately not copied by this command.

### Confirm withdrawals and reallocate cash

Stop the owner service before changing the cash ledger. A withdrawal is performed
manually at HTX; the runner only records its already-completed net cash reduction.
For example, `starslab-runner cash-flow --reference withdrawal-20261006 --trend -20 --dca -10`
records a 30 USDT withdrawal. Live mode verifies that the spot cash balance matches
the resulting tracked cash and that asset holdings still match the journal.

`starslab-runner cash-flow --reference allocation-20261006 --trend 20 --dca -20`
reassigns 20 USDT of current available DCA allocation to trend without changing cash
or contributing a deposit. References are idempotent; changing amounts under an
existing reference is rejected. Pending orders and insufficient allocations block
adjustments. Positive net deposits still use the monthly `fund` command. These
commands never transfer money or submit orders. Net confirmed funding in reports
subtracts withdrawals so a withdrawal is not shown as a trading loss. Withdrawals
of profits beyond net contributions are currently rejected.

### Account valuation history

`starslab-runner history` reads the latest observation from each of the last 168
recorded UTC hours, even while execution holds the journal lock. Future execution
cycles store timestamped valuations locally; no pre-installation history is
fabricated. Each point identifies the hourly research-close price timestamp,
tracked equity and cash, net contributions, actual fees and net investment PnL.
Deposits and withdrawals change contributions alongside equity, so they do not
create an investment profit or loss. These are estimated valuations, excluding
future sell fees. Percentage returns and time-weighted attribution are not yet
provided. History currently remains in the private local journal.

For funding in several deposits during the same UTC month, use
`starslab-runner deposit --reference topup-20261006 --trend 50 --dca 50`
while the owner service is stopped. A unique reference prevents duplicate credits.
Live mode checks the additional free USDT exists. Combined `fund` and `deposit`
credits cannot exceed the configured monthly allocation caps; a withdrawal does
not reset those gross deposit caps. The command never transfers funds or orders.

### Carry unused DCA allocation

Unused DCA credits remain part of tracked cash after their month ends, but do not
automatically become the next month's spending allowance. While the owner service
is stopped, `starslab-runner carry-dca --reference carry-september --from-month 2026-09-01 --amount 30`
explicitly moves 30 USDT of unused September DCA allocation to the current UTC
month. Paired debit/credit records preserve cash and net contributions, and repeated
references do not repeat the transfer. The command rejects current/future source
months, overspending and pending orders. Live mode reconciles and verifies the
spot account first. Carrying does not increase monthly deposit caps or change the
normal daily DCA sizing rule. No new funding, transfer or order is created.

The account_lock_owner configuration names the owner's machine identity, SSH
address, OS user, state directory and executable. The machine identity is a hash
of the local machine ID. A normal init records the current owner; the personal
account designates oracle-arm-002. SSH uses existing owner authentication and
never sends exchange keys or display tokens. Lock helpers only hold a file lock
and answer nonce checks. They have no hosted control endpoint and submit no orders.
