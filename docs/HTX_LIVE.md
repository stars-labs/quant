# Owner-operated HTX spot execution

The platform publishes research signals and displays private account reports.
The independently installed `starslab-runner` trades on the account owner's
computer or server. Exchange credentials and the durable SQLite journal stay
there. A display connection cannot enable trading, change budgets or submit orders.

See [the runner guide](../runner/README.md) for installation, explicit live setup,
confirmed monthly funding, service operation and pending-order recovery.

## Personal deployment

The authorized account uses monthly confirmed funding of 200 USDT: trend 100,
BTC DCA 100, with trend sale proceeds reusable. Its runner is a dedicated personal system service on the owner’s Oracle server,
`owner-starslab-runner.service`. The `starslab-runner` OS user owns its private
state and credentials. Website, collector and Telegram processes cannot read that
state directory. Oracle’s egress IP is already allowlisted; no desktop tunnel is
needed. The NixOS configuration lives in dotfiles under
`nixos-configurations/oracle-arm-002/owner-runner.nix`, with vendored canonical
runner sources. Keep those sources synchronized with `runner/src/starslab_runner/`.

Private configuration, credentials, SQLite accounting and upload-only display
configuration live in `/var/lib/starslab-runner/`. Temporary local credential
storage remains until the owner completes their SOPS update. Do not put credentials
in chat, git or a display report.

Check the service with `systemctl status owner-starslab-runner`. The installed
CLI runs under the private service user:

```bash
sudo -H -u starslab-runner starslab-runner --home /var/lib/starslab-runner status
```

For a new month, deposit first, stop the service, confirm the new funding and restart:

```bash
sudo systemctl stop owner-starslab-runner
sudo -H -u starslab-runner starslab-runner --home /var/lib/starslab-runner fund --trend 100 --dca 100
sudo systemctl start owner-starslab-runner
```

Calendar rollover alone does not confirm a deposit. The funding command checks
available cash and does not transfer money or submit an order. The retired desktop
service and tunnel are removed, its configuration is simulation-only, and its live
journal remains a private inactive archive.

## Private displays and Telegram

[Your accounts](https://starslab.qzz.io/execution) shows the authenticated owner's
allowlisted local reports. The existing Telegram bot reads those same reports for
`/live`, `/trades` and the operator's `/me`. Bound users can query only their own
reports in a private chat. `/livealerts on` opts into fill and report-health
notifications; `/livealerts off` disables them. Other users receive no private
alerts by default. The existing single dispatcher never connects to HTX. A missing or
stale report does not establish whether local execution has stopped. Disconnecting
reporting does not stop trading: stop the local runner to stop execution.

Fees shown are actual reconciled fill fees, including base-asset deductions converted
at the fill price. Equity uses hourly research closes, excludes unconfirmed deposits
and excludes future sale fees. It is an estimate, not an independently verified
exchange statement.

## Cutover accounting

The offline one-time `scripts/import_htx_journal.py` utility imports the stopped
hosted journal into an empty local journal. Original order IDs, action IDs,
exchange IDs, net movements and funding are retained; position names are mapped
to the local runner's names. Absent historical fee quotes stay absent. Actual fill
fees are retained. The original hosted orders/funding are private read-only audit
records; their public execution projection is removed without inventing a sale.

## Owner machine boundary

Live account operations run only as the configured OS user on the designated
owner machine. The personal account uses starslab-runner on oracle-arm-002.
From another computer, SSH to Oracle and use the same private home and journal.
A copied configuration cannot directly execute on another machine or OS user.
Private owner lock routing is preserved during backup; ownership migration
requires stopping and disabling the original service before reassignment.
