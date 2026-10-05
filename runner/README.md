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
