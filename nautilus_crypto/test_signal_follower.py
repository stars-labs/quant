"""Tests for the live signal follower: pure sizing/decision logic, the fill-driven ledger SQL,
and an end-to-end BacktestEngine run (buy on an open public signal, sell when it closes, adopt a
held position, never liquidate on stop, hold when the signal DB is unreadable).

Run: nautilus_equity/.venv/bin/python -c "import sys; sys.path.insert(0,'nautilus_crypto');
     import test_signal_follower as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "strategies"))

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig  # noqa: E402
from nautilus_trader.config import LoggingConfig  # noqa: E402
from nautilus_trader.model.currencies import BTC, USDT  # noqa: E402
from nautilus_trader.model.data import QuoteTick  # noqa: E402
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide  # noqa: E402
from nautilus_trader.model.identifiers import Venue  # noqa: E402
from nautilus_trader.model.objects import Money, Price, Quantity  # noqa: E402
from nautilus_trader.test_kit.providers import TestInstrumentProvider  # noqa: E402

import live_trend  # noqa: E402
import strategy_record  # noqa: E402
from signal_follower import (  # noqa: E402
    SignalFollower, SignalFollowerConfig, asset_of, entry_qty, exit_qty, floor_step, plan,
)
from test_trade_ledger import FakeCursor, FakeLog  # noqa: E402
from trade_ledger import TradeLedger  # noqa: E402


# ------------------------------------------------------------------ pure logic
def test_asset_of_strips_quote_and_venue():
    assert asset_of("PEPEUSDT.BINANCE") == "PEPE"


def test_asset_of_rejects_non_usdt():
    try:
        asset_of("ETHBTC.BINANCE")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_plan_buys_when_signal_open_and_flat():
    assert plan(True, 0.0, False) == "buy"


def test_plan_sells_when_signal_closed_and_holding():
    assert plan(False, 0.5, False) == "sell"


def test_plan_idle_when_aligned():
    assert plan(True, 0.5, False) is None and plan(False, 0.0, False) is None


def test_plan_never_trades_on_unknown_target_or_pending_order():
    assert plan(None, 0.0, False) is None and plan(True, 0.0, True) is None


def test_floor_step_rounds_down():
    assert abs(floor_step(0.123456789, 0.001) - 0.123) < 1e-12


def test_entry_qty_uses_notional():
    assert abs(entry_qty(500, 10_000, 100.0, 0.001, 5.0) - 5.0) < 1e-9


def test_entry_qty_capped_by_free_quote():
    # 98% of 100 USDT free at price 10 → 9.8
    assert abs(entry_qty(500, 100, 10.0, 0.1, 5.0) - 9.8) < 1e-9


def test_entry_qty_zero_below_min_notional():
    # Sep-25 incident: a near-empty USDT balance produced a 0.001 SOL order → -1013 NOTIONAL
    assert entry_qty(500, 0.2, 105.0, 0.001, 5.0) == 0.0


def test_exit_qty_capped_by_free_base():
    assert abs(exit_qty(5.735, 4.0, 100.0, 0.001, 5.0) - 4.0) < 1e-9


def test_exit_qty_zero_when_balance_gone():
    assert exit_qty(0.2, 0.0, 2500.0, 0.0001, 5.0) == 0.0


def test_live_universe_matches_public_record():
    assert live_trend.HOUSE_ASSETS == strategy_record.ASSETS


# ------------------------------------------------------------------ ledger SQL
class RowCursor(FakeCursor):
    def __init__(self, calls, row):
        super().__init__(calls)
        self._row = row

    def fetchone(self):
        return self._row


def _ledger(row=None):
    ledger = TradeLedger(environment="testnet", logger=FakeLog(), asset_class="crypto")
    ledger._url = "postgresql://fake"
    ledger.calls = []
    ledger._cursor = lambda: RowCursor(ledger.calls, row)
    return ledger


def test_open_row_returns_qty_and_rate():
    assert _ledger(row=(0.2068, 1937.8)).open_row("TREND-001", "ETHUSDT.BINANCE") == (0.2068, 1937.8)


def test_open_row_none_when_flat():
    assert _ledger(row=None).open_row("TREND-001", "ETHUSDT.BINANCE") is None


def test_record_exit_closes_open_row_by_instrument():
    ledger = _ledger()
    ledger.record_exit("TREND-001", "ETHUSDT.BINANCE", 1, 2700.0, 0.2, "signal")
    sql, params = ledger.calls[0]
    assert "close_date IS NULL" in sql and params[-2:] == ("TREND-001", "ETHUSDT.BINANCE")


def test_record_entry_skips_backtests():
    ledger = _ledger()
    ledger.record_entry("BACKTESTER-001", "O-1", "S", "ETHUSDT.BINANCE", 1, 1.0, 1.0)
    assert ledger.calls == []


# ------------------------------------------------------------------ engine end-to-end
class ScriptedBook:
    """open_assets() per poll call: a list of return values, the last one repeats."""

    def __init__(self, script):
        self._script = script
        self.calls = 0
        self.last_error = "scripted outage"

    def open_assets(self):
        v = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return v


class SpyLedger:
    def __init__(self):
        self.entries, self.exits = [], []

    def record_entry(self, *a):
        self.entries.append(a)

    def record_exit(self, *a):
        self.exits.append(a)


def _run(script, held_qty=0.0, minutes=30):
    engine = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    inst = TestInstrumentProvider.btcusdt_binance()
    venue = Venue("BINANCE")
    engine.add_venue(venue=venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
                     starting_balances=[Money(10_000, USDT), Money(1, BTC)], base_currency=None)
    engine.add_instrument(inst)
    t0 = 1_758_000_000_000_000_000
    engine.add_data([
        QuoteTick(inst.id, Price.from_str("99999.00"), Price.from_str("100000.00"),
                  Quantity.from_str("10.000000"), Quantity.from_str("10.000000"),
                  t0 + i * 60_000_000_000, t0 + i * 60_000_000_000)
        for i in range(minutes)
    ])
    book, ledger = ScriptedBook(script), SpyLedger()
    strat = SignalFollower(
        SignalFollowerConfig(instrument_id=str(inst.id), notional_usdt=500.0, poll_secs=60,
                             held_qty=held_qty, held_px=90_000.0 if held_qty else 0.0),
        book=book, ledger=ledger,
    )
    engine.add_strategy(strat)
    engine.run()
    sides = [o.side for o in engine.cache.orders()]
    engine.dispose()
    return sides, ledger


def test_engine_buys_once_on_open_signal_and_keeps_it_through_stop():
    sides, ledger = _run([{"BTC"}])
    assert sides == [OrderSide.BUY], sides  # no repeat buys, no liquidation at stop
    assert len(ledger.entries) == 1 and abs(ledger.entries[0][-1] - 0.005) < 1e-9


def test_engine_sells_when_public_signal_closes():
    sides, ledger = _run([{"BTC"}] * 5 + [set()])
    assert sides == [OrderSide.BUY, OrderSide.SELL], sides
    assert ledger.exits and ledger.exits[0][-1] == "signal"


def test_engine_adopts_held_position_without_buying():
    sides, _ = _run([{"BTC"}], held_qty=0.3)
    assert sides == [], sides


def test_engine_sells_adopted_position_when_signal_closed():
    sides, ledger = _run([set()], held_qty=0.3)
    assert sides == [OrderSide.SELL], sides
    assert abs(ledger.exits[0][-2] - 0.3) < 1e-9


def test_engine_holds_when_signal_db_unreadable():
    sides, _ = _run([None], held_qty=0.3)
    assert sides == [], sides


if __name__ == "__main__":
    for name in sorted(n for n in dir() if n.startswith("test_")):
        globals()[name]()
        print("ok", name)
