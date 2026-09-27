"""Live executor for the PUBLIC house signals (quant.strategy_signals) on Binance spot testnet.

Why the node follows the published record instead of computing Donchian itself:
- The record is computed by strategies/signal_evaluator.py on Binance MAINNET 1h bars. Testnet
  bars differ (thin books → spiky highs/lows), so a node running the same rule on testnet bars
  enters/exits at different times than the signals users see.
- A node restart used to lose its in-position state (and on_stop liquidated), leaving the node
  flat while the rule said long. Here the target state lives in the DB (the public record) and
  the holding lives in the execution ledger (quant.nautilus_trades open row), so a restart
  resumes exactly where it left off and on_stop never trades.

Per instrument, every `poll_secs`: target = "the public record has an open trade for this
asset"; holding = qty this strategy bought (seeded from the ledger's open row at start). If
they disagree and no order is in flight, buy `notional_usdt` (capped by free USDT) or sell the
held qty (capped by the free base balance — the testnet account is shared with the
accumulator and is periodically reset). Unknown target (DB error) → do nothing.

The strategy never consults Nautilus positions: the account is shared, so the node also sees
the accumulator's BTC fills as EXTERNAL positions, and an adopted holding has no Nautilus
position at all. The ledger is written from this strategy's own order fills instead.
"""

from __future__ import annotations

import math
import time
from datetime import timedelta

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy

try:
    from trade_ledger import TradeLedger
except ImportError:  # vendored flat in deploy; available there too
    TradeLedger = None

HOUSE_STRATEGY = "donchian_1h"  # quant.strategy_signals.strategy (strategies/strategy_record.py)
QUOTE_BUFFER = 0.98  # keep 2% of free USDT for price moves between quote and fill


# ---------------------------------------------------------------------------- pure logic
def asset_of(instrument_id: str) -> str:
    """'ETHUSDT.BINANCE' -> 'ETH' (the asset key used by quant.strategy_signals)."""
    symbol = instrument_id.split(".")[0]
    if not symbol.endswith("USDT"):
        raise ValueError(f"not a USDT pair: {instrument_id}")
    return symbol[: -len("USDT")]


def plan(target_long: bool | None, held_qty: float, pending: bool) -> str | None:
    """'buy' | 'sell' | None. Unknown target or an order in flight → never trade."""
    if target_long is None or pending:
        return None
    holding = held_qty > 0
    if target_long and not holding:
        return "buy"
    if not target_long and holding:
        return "sell"
    return None


def floor_step(qty: float, step: float) -> float:
    """Round DOWN to the instrument's size increment (never over-buy/over-sell)."""
    if step <= 0:
        return qty
    return math.floor(qty / step + 1e-9) * step


def entry_qty(notional: float, free_quote: float, price: float, step: float,
              min_notional: float) -> float:
    """Base qty for an entry: `notional` USDT, capped by free USDT; 0 if below the exchange
    minimum notional (Binance rejects with -1013 NOTIONAL)."""
    if price <= 0:
        return 0.0
    spend = min(notional, max(free_quote, 0.0) * QUOTE_BUFFER)
    qty = floor_step(spend / price, step)
    return qty if qty > 0 and qty * price >= min_notional else 0.0


def exit_qty(held_qty: float, free_base: float, price: float, step: float,
             min_notional: float) -> float:
    """Base qty for an exit: what we hold, capped by what the account still has; 0 if the
    remainder is dust (unsellable)."""
    qty = floor_step(min(held_qty, max(free_base, 0.0)), step)
    return qty if qty > 0 and qty * price >= min_notional else 0.0


# ---------------------------------------------------------------------------- DB reader
class SignalBook:
    """Reads the set of assets with an OPEN public trade. One instance is shared by all
    strategies of a node; results are cached for `ttl` seconds so a poll tick costs one query."""

    def __init__(self, url: str, strategy: str = HOUSE_STRATEGY, ttl: float = 20.0):
        self._url = url
        self._strategy = strategy
        self._ttl = ttl
        self._conn = None
        self._cached: set[str] | None = None
        self._at = 0.0
        self.last_error: str | None = None

    def _query(self) -> set[str]:
        import psycopg2  # lazily: backtests/--check don't need it

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._url)
            self._conn.autocommit = True
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT asset FROM quant.strategy_signals WHERE strategy = %s AND exit_ts IS NULL",
                (self._strategy,),
            )
            return {r[0] for r in cur.fetchall()}

    def last_close(self, asset: str) -> float | None:
        """The public record's latest mainnet 1h close — the sizing fallback when the testnet
        quote stream never delivers (PEPE's testnet book carries a bid size above Nautilus'
        Quantity limit, so every quote tick is dropped). None on any DB problem."""
        import psycopg2  # lazily

        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg2.connect(self._url)
                self._conn.autocommit = True
            with self._conn.cursor() as cur:
                cur.execute("SELECT last_close FROM quant.strategy_assets "
                            "WHERE strategy = %s AND asset = %s", (self._strategy, asset))
                row = cur.fetchone()
            return float(row[0]) if row and row[0] else None
        except Exception as e:  # noqa: BLE001
            self.last_error = repr(e)
            return None

    def open_assets(self) -> set[str] | None:
        """None when the DB can't be read (caller must then hold, not trade)."""
        now = time.monotonic()
        if self._cached is not None and now - self._at < self._ttl:
            return self._cached
        try:
            self._cached, self._at, self.last_error = self._query(), now, None
        except Exception as e:  # noqa: BLE001 — surfaced via last_error + caller log
            self._cached, self.last_error = None, repr(e)
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
            self._conn = None
        return self._cached


# ---------------------------------------------------------------------------- strategy
class SignalFollowerConfig(StrategyConfig, frozen=True):
    instrument_id: str
    notional_usdt: float = 500.0
    poll_secs: int = 60
    held_qty: float = 0.0     # seeded from the ledger's open row (live_trend.build_node)
    held_px: float = 0.0


class SignalFollower(Strategy):
    def __init__(self, config: SignalFollowerConfig, book: SignalBook, ledger=None):
        super().__init__(config)
        self.iid = InstrumentId.from_str(config.instrument_id)
        self.asset = asset_of(config.instrument_id)
        self._book = book
        self._ledger = ledger
        self._qty = config.held_qty
        self._px = config.held_px
        self._pending = None  # ClientOrderId of the order in flight

    # -- lifecycle
    def on_start(self):
        self.subscribe_quote_ticks(self.iid)  # entry sizing price
        self.clock.set_timer(
            f"poll-{self.asset}", timedelta(seconds=self.config.poll_secs), callback=self._on_poll
        )
        self.log.info(f"{self.asset}: start holding {self._qty} @ {self._px} (from ledger)")

    def on_stop(self):
        # Deliberately NOT liquidating: the holding is in the ledger and resumes on restart.
        self.log.info(f"{self.asset}: stop, keeping holding {self._qty}")

    # -- order events → one finalisation path
    def on_order_filled(self, event):
        self._check_pending()

    def on_order_rejected(self, event):
        self.log.warning(f"{self.asset}: order rejected: {event.reason}")
        self._check_pending()

    def on_order_denied(self, event):
        self.log.warning(f"{self.asset}: order denied: {event.reason}")
        self._check_pending()

    def on_order_canceled(self, event):
        self._check_pending()

    def on_order_expired(self, event):
        self._check_pending()

    # -- the loop
    def _on_poll(self, _event=None):
        self._check_pending()  # also recovers from a missed order event
        open_assets = self._book.open_assets()
        target = None if open_assets is None else self.asset in open_assets
        if target is None:
            self.log.warning(f"{self.asset}: signal DB unreadable, holding ({self._book.last_error})")
            return
        action = plan(target, self._qty, self._pending is not None)
        if action == "buy":
            self._buy()
        elif action == "sell":
            self._sell()

    def _instrument_and_account(self):
        instrument = self.cache.instrument(self.iid)
        account = self.portfolio.account(self.iid.venue)
        if instrument is None or account is None:
            self.log.warning(f"{self.asset}: instrument/account not ready")
            return None, None
        return instrument, account

    @staticmethod
    def _min_notional(instrument) -> float:
        mn = getattr(instrument, "min_notional", None)
        return float(mn) if mn is not None else 0.0

    @staticmethod
    def _free(account, currency) -> float:
        bal = account.balance_free(currency)
        return float(bal) if bal is not None else 0.0

    def _buy(self):
        instrument, account = self._instrument_and_account()
        if instrument is None:
            return
        quote = self.cache.quote_tick(self.iid)
        if quote is not None:
            price = float(quote.ask_price)
        else:
            # A market order only needs a price to size it; the public record's last close
            # is close enough (and it is the price users were shown).
            price = self._book.last_close(self.asset)
            if not price:
                self.log.warning(f"{self.asset}: no quote and no public close, entry deferred")
                return
            self.log.info(f"{self.asset}: no testnet quote — sizing off the public close {price}")
        qty = entry_qty(self.config.notional_usdt, self._free(account, instrument.quote_currency),
                        price, float(instrument.size_increment), self._min_notional(instrument))
        if qty <= 0:
            self.log.warning(f"{self.asset}: entry skipped — free "
                             f"{instrument.quote_currency} below the minimum notional")
            return
        order = self.order_factory.market(self.iid, OrderSide.BUY, instrument.make_qty(qty))
        self._pending = order.client_order_id
        self.submit_order(order)
        self.log.info(f"{self.asset}: public signal LONG → BUY {qty} (~{qty * price:.2f} USDT)")

    def _sell(self):
        instrument, account = self._instrument_and_account()
        if instrument is None:
            return
        quote = self.cache.quote_tick(self.iid)
        price = float(quote.bid_price) if quote is not None else self._px
        qty = exit_qty(self._qty, self._free(account, instrument.base_currency), price,
                       float(instrument.size_increment), self._min_notional(instrument))
        if qty <= 0:
            # Testnet reset / sold elsewhere: nothing left to sell. Close the ledger row
            # without a price so no fake PnL is recorded.
            self.log.warning(f"{self.asset}: public signal FLAT but holding {self._qty} is no "
                             "longer in the account — closing the ledger row as balance_gone")
            if self._ledger:
                self._ledger.record_exit(self.trader_id, self.iid, self.clock.timestamp_ns(),
                                         None, 0.0, "balance_gone")
            self._qty, self._px = 0.0, 0.0
            return
        order = self.order_factory.market(self.iid, OrderSide.SELL, instrument.make_qty(qty))
        self._pending = order.client_order_id
        self.submit_order(order)
        self.log.info(f"{self.asset}: public signal FLAT → SELL {qty}")

    def _check_pending(self):
        if self._pending is None:
            return
        order = self.cache.order(self._pending)
        if order is None or not order.is_closed:
            return
        self._pending = None
        filled = float(order.filled_qty)
        if filled <= 0:
            return  # rejected/denied/canceled: retry on the next poll
        if order.side == OrderSide.BUY:
            self._qty, self._px = filled, float(order.avg_px)
            if self._ledger:
                self._ledger.record_entry(self.trader_id, str(order.client_order_id), str(self.id),
                                          self.iid, order.ts_last, self._px, filled)
        else:
            if self._ledger:
                self._ledger.record_exit(self.trader_id, self.iid, order.ts_last,
                                         float(order.avg_px), filled, "signal")
            self._qty, self._px = 0.0, 0.0  # any unsold remainder is dust
