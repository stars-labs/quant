# HTX live spot operation

Dedicated UID597216794 / spot73961187. User-authorized monthly contribution200 USDT: trend100, BTC DCA100. Gate and Binance stay dry-run/testnet.

Trend entries spend at most20 USDT including fee headroom; unused capital and net exit proceeds can be reused. The initial startup follows currently open house signals. DCA daily base is100 / days in the UTC month, multiplied by today's smart-DCA units and capped at the funded monthly100. No catch-up for previous days. Orders below venue minimum are skipped. Unspent prior-month DCA stays in cash and is not reassigned to trend.

## Funding a new month

Deposit200 USDT into the dedicated spot account, then stop `quant-executor` and run `scripts/htx_funding.py` on arm-002 with its environment. The script verifies account UID and additional free cash, records100/100 once for the current UTC month and never transfers funds or submits orders. Restart the service afterward. Calendar rollover does not invent a new deposit; trend existing capital may still recycle while DCA pauses until the new month is funded. Do not manually trade, withdraw or add assets to this account while the bot runs; journal/balance mismatch pauses trading.

## Runtime secrets (temporary)

`/run/quant-htx-runtime.env` is0600, owned by nautilus, consumed only by quant-executor. It contains HTX_API_KEY and HTX_API_SECRET and disappears after reboot. Missing file prevents service startup. User requested this temporary mode before configuring SOPS.

To replace it: add encrypted `oracle-arm-002/htx-api-key` and `oracle-arm-002/htx-api-secret` entries in dotfiles secrets/common.yaml; declare corresponding sops.secrets and an executor-only sops template exporting HTX_API_KEY/_SECRET; replace the runtime EnvironmentFile/ConditionPathExists with the SOPS template. Keep the collectors' existing DB environment file. Rebuild and verify UID/holdings after rotating the key. Never put keys in Nix source, shell history, logs or git.

## Order recovery

Every real order is preceded by a committed quant.executor_orders intent and unique client ID. Unknown HTTP results stay pending. A restart queries the existing order; it never resubmits a pending intent. Terminal actual matches, base/quote fees and ledger projection commit together. Missing details, third-currency fees, stale house bars or mismatched balances pause HTX. Partial sells preserve remaining holdings; unsellable dust remains recorded. Quant health checks monitor executor_status.

Inspect `journalctl -u quant-executor`, executor_status and pending executor_orders. Never delete an unknown intent to force a retry. HTX client-ID queries have a time window: investigate against the exchange's order history before making any correction. To stop trading: `systemctl stop quant-executor` (does not sell holdings).

## Verification

Offline tests: tests/test_htx_live.py; PostgreSQL integration: tests/test_htx_orders_db.py with CCXT_TEST_DSN targeting an EMPTY disposable DB. Read-only credential test: scripts/htx_preflight.py. Rebuild and first-fill evidence lives in docs/changes/2026-10-05-htx-live.md.
