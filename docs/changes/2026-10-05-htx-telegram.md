# HTX private Telegram reminders

The existing single alert dispatcher now sends HTX live execution reminders only to
TELEGRAM_CHAT_ID. Completed fills are grouped (up to20), with fee-adjusted quantity,
USDT spent/net proceeds, and current trend/monthly-DCA budget. Failed sends retain
unacknowledged rows; migration040 adds notified_at for restart-safe acknowledgements.
Execution errors/stale heartbeat and recovery notify on transitions. Missing funding
notifies once per UTC month using the dispatcher's existing persistent state.

Validation:

- Python plain-function harness:143 tests passed across test_htx_notifications,
  test_htx_live, test_ccxt_executor, test_health_check, test_htx_preflight,
  test_alert_dispatcher.
- Disposable PostgreSQL: notification migration, failed-send retry and acknowledgement
  surviving a new dispatcher state passed; live journal budgets/fees/partial exits/
  replay/rollback/advisory lock/month rollover also passed.
- Production migration040 applied successfully.
- NixOS background rebuild completed with ExecMainStatus=0, generation
  /nix/store/dy907pqlz5nfrmnm485cnh30rwba60fa-nixos-system-oracle-arm-002-26.11.20261003.a7868a7.
- quant-executor and quant-alert-dispatcher active; dispatcher NRestarts=0.
- Production HTX journal:6 done,0 pending,6 notified. Latest initial notification
  acknowledgement2026-10-05T10:49:55.097556Z; executor status healthy=true/detail=ok.
  Real delivery was verified through acknowledgement after Telegram API success;
  simulated failures/recoveries were tested offline, not induced on the live account.

Runtime secret arrangement and trading policy are unchanged. Telegram timeout ambiguity
can duplicate a reminder but cannot place a trade. Existing PostgreSQL collation warning
is unrelated and remains unresolved.

Deployment commits: quant3fc7dcc, nur7a55f4c, dotfiles20653243.
