"""Tests for TradeLedger SQL: restart supersede + open-row-only close (no DB, fake cursor)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nautilus_trader.model.enums import PositionSide  # noqa: E402
from trade_ledger import TradeLedger  # noqa: E402

TS_OPEN = 1_758_000_000_000_000_000
TS_CLOSE = TS_OPEN + 3_600_000_000_000


class FakeCursor:
    def __init__(self, calls, fail=False):
        self._calls = calls
        self._fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        if self._fail:
            raise RuntimeError("db down")
        self._calls.append((" ".join(sql.split()), params))


class FakeLog:
    def __init__(self):
        self.warnings = []

    def warning(self, msg):
        self.warnings.append(msg)


def _ledger(fail=False):
    ledger = TradeLedger(environment="testnet", logger=FakeLog(), asset_class="crypto")
    ledger._url = "postgresql://fake"
    ledger.calls = []
    ledger._cursor = lambda: FakeCursor(ledger.calls, fail=fail)
    return ledger


def _event(trader_id="TRADER-001", ts_opened=TS_OPEN):
    return SimpleNamespace(
        trader_id=trader_id, position_id="BTCUSDT.BINANCE-DONCHIAN-000",
        strategy_id="DonchianTrend-000", instrument_id="BTCUSDT.BINANCE",
        side=PositionSide.LONG, ts_opened=ts_opened, avg_px_open=100_000.0, quantity=0.01,
        ts_closed=TS_CLOSE, avg_px_close=101_000.0, realized_pnl=10.0, realized_return=0.01,
    )


def test_record_open_supersedes_before_insert():
    ledger = _ledger()
    ledger.record_open(_event())
    assert [sql.split()[0] for sql, _ in ledger.calls] == ["UPDATE", "INSERT"]


def test_supersede_sets_superseded_close_at_new_open():
    ledger = _ledger()
    ledger.record_open(_event())
    sql, params = ledger.calls[0]
    assert "close_date = to_timestamp(%s/1e9), exit_reason = 'superseded'" in sql
    assert params == (TS_OPEN, "TRADER-001", "BTCUSDT.BINANCE-DONCHIAN-000", TS_OPEN)


def test_supersede_only_touches_older_unclosed_rows():
    # on_position_changed re-calls record_open with the SAME ts_opened; strict `<` means
    # the current incarnation never supersedes itself.
    ledger = _ledger()
    ledger.record_open(_event())
    sql, _ = ledger.calls[0]
    assert "AND close_date IS NULL AND open_date < to_timestamp(%s/1e9)" in sql


def test_repeat_open_same_ts_uses_upsert_not_new_row():
    ledger = _ledger()
    ledger.record_open(_event())
    ledger.record_open(_event())
    inserts = [p for sql, p in ledger.calls if sql.startswith("INSERT")]
    assert "ON CONFLICT (trader_id, position_id, open_date) DO UPDATE" in ledger.calls[1][0]
    assert inserts[0] == inserts[1]


def test_record_close_only_updates_open_row():
    ledger = _ledger()
    ledger.record_close(_event())
    sql, params = ledger.calls[0]
    assert sql.endswith("WHERE trader_id = %s AND position_id = %s AND close_date IS NULL")
    assert params[-2:] == ("TRADER-001", "BTCUSDT.BINANCE-DONCHIAN-000")


def test_backtest_trader_ids_are_ignored():
    ledger = _ledger()
    ledger.record_open(_event(trader_id="BACKTESTER-001"))
    ledger.record_close(_event(trader_id="BACKTESTER-001"))
    assert ledger.calls == []


def test_db_errors_are_swallowed_and_logged():
    ledger = _ledger(fail=True)
    ledger.record_open(_event())
    ledger.record_close(_event())
    assert len(ledger._log.warnings) == 2
