"""Tests for strategies/ccxt_executor.py — decisions, venue fills (fake ccxt), trend loop.

Run: .venv-bots/bin/python -c "import sys; sys.path.insert(0,'tests'); import test_ccxt_executor as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

import ccxt_executor as ce  # noqa: E402


class FakeEx:
    def __init__(self, usdt=1_000.0, coin=0.0):
        self.markets = {"BTC/USDT": {"taker": 0.002, "limits": {"cost": {"min": 5}}},
                        "ETH/USDT": {"taker": 0.002, "limits": {"cost": {"min": 5}}}}
        self.balances = {"USDT": usdt, "BTC": coin, "ETH": coin}
        self.orders = []

    def load_markets(self):
        return self.markets

    def fetch_ticker(self, sym):
        return {"ask": 101.0, "bid": 99.0}

    def amount_to_precision(self, sym, amount):
        return f"{int(amount * 1000) / 1000:.3f}"

    def fetch_balance(self):
        return {"free": dict(self.balances)}

    def create_market_buy_order_with_cost(self, sym, cost):
        self.orders.append(("buy", sym, cost))
        return {"id": "1", "symbol": sym, "filled": cost / 100.0, "average": 100.0}

    def create_market_sell_order(self, sym, amount):
        self.orders.append(("sell", sym, amount))
        return {"id": "2", "symbol": sym, "filled": amount, "average": 98.0}


def test_parse_venues_defaults_and_guardrail():
    assert ce.parse_venues("gate:testnet, HTX", False) == [("gate", "testnet"), ("htx", "dry_run")]
    for bad in ("htx:live", "gate:paper"):
        try:
            ce.parse_venues(bad, False)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert ce.parse_venues("htx:live", True) == [("htx", "live")]


def test_trend_actions_mirror_signals():
    acts = ce.trend_actions({"BTC"}, {"ETH": 1.0}, ("BTC", "ETH", "SOL"))
    assert acts == [("buy", "BTC"), ("sell", "ETH")]


def test_trend_actions_hold_when_signals_unreadable():
    assert ce.trend_actions(None, {"ETH": 1.0}, ("BTC", "ETH")) == []


def test_realized_is_net_of_both_fees():
    pnl, ret = ce.realized(100.0, 110.0, 2.0, 0.002)
    assert abs(pnl - (20.0 - 2.0 * 210.0 * 0.002)) < 1e-9
    assert abs(ret - (110 * 0.998 / (100 * 1.002) - 1)) < 1e-12


def test_dry_run_buy_fills_at_ask_without_orders():
    ex = FakeEx()
    v = ce.Venue("gate", "dry_run", ex)
    f = v.buy("BTC", 500.0)
    assert (f.qty, f.price) == (4.95, 101.0) and ex.orders == []


def test_dry_run_sell_fills_at_bid():
    v = ce.Venue("htx", "dry_run", FakeEx())
    assert v.sell("ETH", 2.0) == ce.Fill(2.0, 99.0)


def test_testnet_buy_is_capped_by_free_usdt():
    ex = FakeEx(usdt=300.0)
    f = ce.Venue("gate", "testnet", ex).buy("BTC", 500.0)
    assert ex.orders == [("buy", "BTC/USDT", 300.0)] and f == ce.Fill(3.0, 100.0)


def test_testnet_buy_skipped_below_minimum():
    ex = FakeEx(usdt=3.0)
    assert ce.Venue("gate", "testnet", ex).buy("BTC", 500.0) is None and ex.orders == []


def test_testnet_sell_capped_by_free_coin():
    ex = FakeEx(coin=0.5)
    f = ce.Venue("gate", "testnet", ex).sell("ETH", 2.0)
    assert ex.orders == [("sell", "ETH/USDT", 0.5)] and f.qty == 0.5


class FakeLedger:
    def __init__(self, rows):
        self.rows, self.adds, self.closes = rows, [], []

    def open_rows(self, kind, venue):
        return dict(self.rows)

    def add(self, kind, venue, asset, fill, row):
        self.adds.append((kind, asset, fill))

    def close(self, kind, venue, asset, row, fill, fee):
        self.closes.append((kind, asset, fill))


def test_run_trend_buys_new_signals_and_sells_closed_ones(monkey=None):
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    ledger = FakeLedger({"ETH": (t0, 100.0, 2.0, t0)})
    v = ce.Venue("gate", "dry_run", FakeEx())
    orig_assets, orig_sig = ce.sr.ASSETS, ce.open_signals
    ce.sr.ASSETS, ce.open_signals = ("BTC", "ETH"), (lambda conn: {"BTC"})
    try:
        ce.run_trend(None, v, ledger, 500.0)
    finally:
        ce.sr.ASSETS, ce.open_signals = orig_assets, orig_sig
    assert [(k, a) for k, a, _ in ledger.adds] == [("trend", "BTC")]
    assert [(k, a, f.price) for k, a, f in ledger.closes] == [("trend", "ETH", 99.0)]


class DcaConn:
    def __init__(self, rule):
        self.rule = rule

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, *args):
        pass

    def fetchone(self):
        return self.rule


def test_dca_requires_current_utc_rule():
    from datetime import timedelta

    today = datetime.now(timezone.utc).date()
    for day in (today - timedelta(days=1), today + timedelta(days=1)):
        ledger = FakeLedger({})
        ce.run_dca(DcaConn((day, 2)), ce.Venue('gate', 'dry_run', FakeEx()), ledger, 100)
        assert ledger.adds == []


def test_dca_buys_current_rule_and_skips_same_day_repeat():
    now = datetime.now(timezone.utc)
    ledger = FakeLedger({})
    venue = ce.Venue('gate', 'dry_run', FakeEx())
    ce.run_dca(DcaConn((now.date(), 2)), venue, ledger, 100)
    assert ledger.adds == [('dca', 'BTC', ce.Fill(1.98, 101.0))]
    ledger.rows['BTC'] = (now, 101, 1.98, now)
    ce.run_dca(DcaConn((now.date(), 2)), venue, ledger, 100)
    assert len(ledger.adds) == 1


def test_dca_missing_rule_holds():
    ledger = FakeLedger({})
    ce.run_dca(DcaConn(None), ce.Venue('gate', 'dry_run', FakeEx()), ledger, 100)
    assert ledger.adds == []
