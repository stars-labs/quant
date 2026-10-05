# Existing Telegram bot: private HTX live account

The operator's private chat now shows the actual HTX account for bare /start, /me
and /live, and the last10 confirmed real fills for /trades. Both the private chat
and sender ID must match TELEGRAM_CHAT_ID. Public follow records and binding-token
flows remain available to subscribers. The owner has a scoped Telegram command
menu and a reply keyboard. Initial account overview delivery is retried until
successful, using the existing dispatcher state. No second bot or update consumer.

Account values come from the private HTX/live order and funding journal, with trend
and DCA holdings separated. Costs and cash movements include actual fees. Realized
PnL includes partial sales. Equity and total PnL use dated, cached hour-close prices;
missing, future, nonfinite or older-than3h marks suppress totals. Cash is confirmed
journal cash, not a new exchange balance fetch. No trading credentials are given
to the dispatcher and queries cannot place orders.

Evidence:

- Plain Python harness:151 tests passed (account access/routing/menu retry/valuation,
  existing notifications, live execution, health, preflight and public dispatcher).
- NixOS rebuild ExecMainStatus=0; generation
  /nix/store/llsi2jn5j714fxq6icpr2bin7yjih66k-nixos-system-oracle-arm-002-26.11.20261003.a7868a7.
- Both executor and dispatcher active; read-only installed-module queries succeeded
  against production using the quant role.
- Telegram getMyCommands for the owner scope returned live,trades,me. Persistent
  htx_menu_version=1 confirms the initial account overview send succeeded.
- Production account at2026-10-05T14:41Z: confirmed contributions200.00 USDT,
  journal cash97.08, pending0, trend budget0.30, October DCA budget96.78.
  Dated hour-close marks (oldest13:59Z) estimated equity199.71/total PnL-0.29 USDT.
  These are validation snapshots, not current quotes. Existing real-fill query works.

Commits: quant32b1445, nur10a6ef0, dotfilesecae7cf3.
