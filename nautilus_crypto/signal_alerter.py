"""Nautilus Actor: the single-stack signal layer.

Subscribes to minute bars and emits explainable Telegram event cards. Detection lives in
``signal_detect.py``; optional futures context is loaded only when an event fires.

Add it to a TradingNode subscribed to REAL (mainnet) public market data — spike/dip
signals must reflect live prices even while execution runs on testnet.
"""

from __future__ import annotations

from nautilus_trader.common.actor import Actor
from nautilus_trader.model.data import Bar, BarType

from signal_detect import DipDetector, SpikeDetector
from signal_context import MarketContextFetcher, SignalContext
from telegram_notifier import TelegramNotifier


class SignalAlerter(Actor):
    def __init__(
        self,
        instrument_ids,
        bar_spec: str = "1-MINUTE-LAST-EXTERNAL",
        notifier: TelegramNotifier | None = None,
        context_fetcher: MarketContextFetcher | None = None,
    ):
        super().__init__()
        # Accept instrument objects (backtest) or id strings (live, where instruments load
        # async and aren't available at construction) — normalise to "SYMBOL.VENUE" strings.
        self._iids = [str(getattr(i, "id", i)) for i in instrument_ids]
        self._bar_spec = bar_spec
        self._notifier = notifier or TelegramNotifier()
        self._context = context_fetcher
        self._spike: dict = {}
        self._dip: dict = {}

    def on_start(self):
        for iid in self._iids:
            bt = BarType.from_str(f"{iid}-{self._bar_spec}")
            self.subscribe_bars(bt)
            self._spike[iid] = SpikeDetector()
            self._dip[iid] = DipDetector()
        if self._notifier.enabled:
            syms = ", ".join(iid.split(".")[0] for iid in self._iids)
            # One-time heartbeat: confirms the live creds→Telegram path and tells the
            # operator the node is watching. Only re-fires on restart/redeploy.
            self._notifier.send(
                f"🟢 *Signal node online*\nWatching {syms} for spike + accumulation-dip alerts."
            )
        else:
            self.log.warning(
                "SignalAlerter: TelegramNotifier disabled (no creds) — detecting but not sending"
            )

    def on_bar(self, bar: Bar):
        iid = str(bar.bar_type.instrument_id)
        ts = bar.ts_event / 1e9
        price = float(bar.close)
        sym = iid.split(".")[0]

        sp = self._spike[iid].update(ts, price)
        if sp:
            self.log.info(f"spike {sym} {sp['kind']} {sp['change_pct']:+.2%}")
            self._notifier.send(self._fmt_spike(sym, sp, self._fetch_context(sym, sp)))

        dp = self._dip[iid].update(ts, price)
        if dp:
            self.log.info(f"dip {sym} {dp['kind']} {dp['change_pct']:+.2%}")
            self._notifier.send(self._fmt_dip(sym, dp, self._fetch_context(sym, dp)))

    def _fetch_context(self, sym: str, event: dict) -> SignalContext | None:
        if self._context is None:
            return None
        return self._context.fetch(sym, event["change_pct"])

    @staticmethod
    def _fmt_spike(sym: str, e: dict, context: SignalContext | None = None) -> str:
        arrow = "📈" if e["kind"] == "PUMP" else "📉"
        mins = int(e["window_sec"] / 60)
        message = (
            f"{arrow} *{e['kind']}* `{sym}`\n"
            f"Move: `{e['change_pct']:+.2%}` in {mins}m\n"
            f"Price: `${e['price']:,.2f}` (from `${e['from_price']:,.2f}`)"
        )
        return SignalAlerter._with_context(message, context)

    @staticmethod
    def _fmt_dip(sym: str, e: dict, context: SignalContext | None = None) -> str:
        mins = int(e["window_sec"] / 60)
        message = (
            f"🎯 *Accumulation dip* `{sym}` ({e['kind']})\n"
            f"Drop: `{e['change_pct']:+.2%}` in {mins}m\n"
            f"Price: `${e['price']:,.2f}` (from `${e['from_price']:,.2f}`)"
        )
        return SignalAlerter._with_context(message, context)

    @staticmethod
    def _with_context(message: str, context: SignalContext | None) -> str:
        if context is None:
            return message
        return (
            f"{message}\n\n"
            f"*结构*: {context.structure}\n"
            f"*置信度*: {context.confidence}\n"
            f"*证据*: {' · '.join(context.evidence)}\n"
            f"*观察*: {context.watch}"
        )
