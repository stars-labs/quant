# HTX live spot operation

Dedicated UID597216794 / spot73961187. User-authorized monthly contribution200 USDT: trend100, BTC DCA100. Gate and Binance stay dry-run/testnet.

Trend entries spend at most20 USDT including fee headroom; unused capital and net exit proceeds can be reused. The initial startup follows currently open house signals. DCA daily base is100 / days in the UTC month, multiplied by today's smart-DCA units and capped at the funded monthly100. No catch-up for previous days. Orders below venue minimum are skipped. Unspent prior-month DCA stays in cash and is not reassigned to trend.

Before every actual buy or sell, authenticated CCXT fetch_trading_fee reads HTX
GET /v2/reference/transact-fee-rate for that symbol, using actualTakerRate instead
of a public/default VIP table. The queried effective rate is logged; missing,
invalid or mismatched results prevent the order. Both the effective rate and basic
takerFeeRate must fit the0.30% safety ceiling, covering discount exhaustion between
query and fill. This ceiling is only cash headroom, never the fee charged in PnL.
Actual finalized match fees drive net quantities/cash/PnL. Ongoing deduction pauses
reconciliation; HT/point deductions remain unsupported and pause even when CCXT
only exposes the base/quote component. Do not enable these without journal support.
Read-only verification on2026-10-05 returned0.15% effective maker/taker and0.20%
basic rates for all13 house pairs; these values are observations, not fixed settings.
The endpoint reports applicable rates, not a VIP level; do not infer the user's tier.

## Funding a new month

Deposit200 USDT into the dedicated spot account, then stop `quant-executor` and run the installed `htx_funding.py` on arm-002 with the executor environment (the script is next to `ccxt_executor.py` in the immutable app directory shown by `systemctl show quant-executor -p ExecStart --value`). The source copy is `scripts/htx_funding.py`. The script verifies account UID and additional free cash, records100/100 once for the current UTC month and never transfers funds or submits orders. Restart the service afterward. Calendar rollover does not invent a new deposit; trend existing capital may still recycle while DCA pauses until the new month is funded. Do not manually trade, withdraw or add assets to this account while the bot runs; journal/balance mismatch pauses trading.

## Runtime secrets (temporary)

`/run/quant-htx-runtime.env` is0600, owned by nautilus, consumed only by quant-executor. It contains HTX_API_KEY and HTX_API_SECRET and disappears after reboot. Missing file prevents service startup. User requested this temporary mode before configuring SOPS.

To replace it: add encrypted `oracle-arm-002/htx-api-key` and `oracle-arm-002/htx-api-secret` entries in dotfiles secrets/common.yaml; declare corresponding sops.secrets and an executor-only sops template exporting HTX_API_KEY/_SECRET; replace the runtime EnvironmentFile/ConditionPathExists with the SOPS template. Keep the collectors' existing DB environment file. Rebuild and verify UID/holdings after rotating the key. Never put keys in Nix source, shell history, logs or git.

## Order recovery

Every real order is preceded by a committed quant.executor_orders intent and unique client ID. Unknown HTTP results stay pending. A restart queries the existing order; it never resubmits a pending intent. Terminal actual matches, base/quote fees and ledger projection commit together. Missing details, third-currency fees, stale house bars or mismatched balances pause HTX. Partial sells preserve remaining holdings; unsellable dust remains recorded. Quant health checks monitor executor_status.

Inspect `journalctl -u quant-executor`, executor_status and pending executor_orders. Never delete an unknown intent to force a retry. HTX client-ID queries have a time window: investigate against the exchange's order history before making any correction. To stop trading: `systemctl stop quant-executor` (does not sell holdings).

## Verification

The existing single alert dispatcher has an owner-scoped command menu. In the owner's private chat, /start
(without a binding token), /me and /live show actual holdings, confirmed journal cash,
budgets and PnL; /trades shows the latest10 actual fills. Queries require both the
private chat ID and sender ID to match TELEGRAM_CHAT_ID. Other users keep their follow
record and cannot query this account. No trading or transfer commands are exposed.
Valuation uses cached hour-close house prices, explicitly dated; missing, future or
older-than3h prices suppress total equity/PnL. Net fees are included in cost and cash,
but future liquidation fees are not. Extra deposits require funding confirmation.

Private Telegram reminders use the existing single alert dispatcher and TELEGRAM_CHAT_ID;
personal HTX trades are never broadcast to signal subscribers. Confirmed fills include net
quantity, fee-inclusive cash movements and current trend/monthly-DCA budgets. Successful
delivery is acknowledged in executor_orders.notified_at; failed sends retry. An ambiguous
Telegram network timeout can duplicate a reminder, but cannot submit a trade. Paused/stale
execution and recovery are notified on transitions; missing monthly funding is reminded
once per UTC month. The dispatcher state file retains transition/reminder acknowledgements.
The first deployment also reports previously completed, unnotified fills as a single batch.

Offline tests: tests/test_htx_live.py; PostgreSQL integration: tests/test_htx_orders_db.py with CCXT_TEST_DSN targeting an EMPTY disposable DB. Read-only credential test: scripts/htx_preflight.py. Rebuild and first-fill evidence lives in docs/changes/2026-10-05-htx-live.md.
