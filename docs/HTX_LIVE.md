# Owner-operated HTX spot execution

The platform publishes research signals and displays private account reports.
The independently installed `starslab-runner` trades on the account owner's
computer or server. Exchange credentials and the durable SQLite journal stay
there. A display connection cannot enable trading, change budgets or submit orders.

See [the runner guide](../runner/README.md) for installation, explicit live setup,
confirmed monthly funding, service operation and pending-order recovery.

## Personal deployment

The authorized account uses monthly confirmed funding of 200 USDT: trend 100,
BTC DCA 100, with trend sale proceeds reusable. Its runner is a game-box user
service, `starslab-runner.service`; `starslab-runner-egress.service` carries HTTPS
through the owner's allowlisted server. No exchange keys reside on the display
server. Source units live in `systemd/`, installed copies in the user's systemd
directory. Keep both copies in sync.

Private configuration, credentials, SQLite accounting and upload-only display
configuration live in `~/.config/starslab-runner/`. Temporary local credential
storage remains until the owner completes their SOPS update. Do not put credentials
in chat, git or a display report.

Check the local service with `systemctl --user status starslab-runner` and the
runner with `starslab-runner status`. Stop the runner before confirming a new
month's funding with `starslab-runner fund --trend 100 --dca 100`; a calendar
change alone does not confirm a deposit. Restart it afterward. The funding command
checks available cash and does not transfer money or submit an order.

## Private displays and Telegram

[Your accounts](https://starslab.qzz.io/execution) shows the authenticated owner's
allowlisted local reports. The existing Telegram bot reads those same reports for
`/live`, `/trades` and the operator's `/me`. It never connects to HTX. A missing or
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
