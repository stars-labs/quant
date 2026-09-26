"""Unit tests for the house-strategy sweep in strategies/signal_evaluator.py (migration 032):
the live path, and the outage catch-up — when the evaluator was down longer than the fetched
window, the missed bars are re-fetched and replayed exactly, and whatever they trigger is
written as backfill (live=false, pre-notified), never as late live calls.

Fake connection/cursor and patched Binance fetchers — no DB, no network.

Plain test_* functions with bare asserts — runs under pytest or the stdlib harness:
  P=nautilus_equity/.venv/bin/python
  $P -c "import sys; sys.path.insert(0,'tests'); import test_house_sweep as t; \
[getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Strategy modules live in strategies/ at the repo root and have no __init__.py.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "strategies"))

import signal_evaluator as se  # noqa: E402
from strategy_record import ENTRY_LB  # noqa: E402

H = 3_600_000  # one hour in ms
T0 = 1_767_225_599_999  # 2025-12-31 23:59:59.999 UTC — a Binance 1h close_time


def flat(n: int, start: int = 0, high: float = 100.0, low: float = 90.0, close: float = 95.0):
    return [(T0 + (start + k) * H, high, low, close) for k in range(n)]


def bar(idx: int, high: float, low: float, close: float):
    return (T0 + idx * H, high, low, close)


def at(idx: int) -> datetime:
    return se._ms_to_dt(T0 + idx * H)


# Bars 0..167 warm up a [90, 100] channel; bar 168 closes at 101 → entry. The rest stay long
# (closes 98 never break the trailing low), so the full replay is exactly one entry.
ENTRY_BAR = [bar(ENTRY_LB, 102, 94, 101)]
EXIT_BAR = [bar(ENTRY_LB, 95, 85, 89)]
HISTORY = flat(ENTRY_LB) + ENTRY_BAR + flat(600, start=ENTRY_LB + 1, high=102, low=94, close=98)


class FakeConn:
    """Stored state for one asset (what _house_resume reads) + every write."""

    def __init__(self, open_row=None, last_event=None, last_ts=None):
        self.open_row, self.last_event, self.last_ts = open_row, last_event, last_ts
        self.writes: list[tuple[str, tuple]] = []

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeCursor:
    def __init__(self, conn: FakeConn):
        self.conn, self.row, self.rowcount = conn, None, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        if q.startswith("SELECT entry_ts, entry_price"):
            self.row = self.conn.open_row
        elif q.startswith("SELECT max("):
            self.row = (self.conn.last_event,)
        elif q.startswith("SELECT last_ts"):
            self.row = (self.conn.last_ts,) if self.conn.last_ts else None
        else:
            self.conn.writes.append((q, params))
            self.rowcount = 1

    def fetchone(self):
        return self.row


def signal_writes(conn: FakeConn) -> list[tuple[str, tuple]]:
    return [(q.split()[0], p) for q, p in conn.writes if "quant.strategy_signals" in q]


@contextmanager
def patched(mod, **attrs):
    old = {k: getattr(mod, k) for k in attrs}
    for k, v in attrs.items():
        setattr(mod, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(mod, k, v)


# ---------- _sweep_house_asset: live vs catch-up writes ----------

def flat_through_167() -> FakeConn:
    return FakeConn(last_ts=at(ENTRY_LB - 1))


def long_through_167() -> FakeConn:
    return FakeConn(open_row=(at(-1), 95.0), last_event=at(-1), last_ts=at(ENTRY_LB - 1))


def test_live_entry_is_live_and_unnotified():
    conn = flat_through_167()
    se._sweep_house_asset(conn, "BTC", flat(ENTRY_LB) + ENTRY_BAR)
    (kind, params), = signal_writes(conn)
    assert (kind, params[-2:]) == ("INSERT", (True, None))


def test_catch_up_entry_is_backfill_and_prenotified():
    conn = flat_through_167()
    se._sweep_house_asset(conn, "BTC", flat(ENTRY_LB) + ENTRY_BAR, catch_up=True)
    (_, params), = signal_writes(conn)
    assert (params[-2], isinstance(params[-1], datetime)) == (False, True)


def test_live_exit_leaves_exit_unnotified():
    conn = long_through_167()
    se._sweep_house_asset(conn, "BTC", flat(ENTRY_LB) + EXIT_BAR)
    (kind, params), = signal_writes(conn)
    assert (kind, params[3]) == ("UPDATE", None)


def test_catch_up_exit_is_prenotified():
    conn = long_through_167()
    se._sweep_house_asset(conn, "BTC", flat(ENTRY_LB) + EXIT_BAR, catch_up=True)
    (_, params), = signal_writes(conn)
    assert isinstance(params[3], datetime)


def test_bars_not_reaching_back_to_last_processed_bar_raise_and_write_nothing():
    conn = FakeConn(last_ts=at(-10))  # processed up to 10 bars before the given ones
    try:
        se._sweep_house_asset(conn, "BTC", flat(ENTRY_LB) + ENTRY_BAR)
        raised = False
    except RuntimeError:
        raised = True
    assert (raised, conn.writes) == (True, [])


def test_asset_without_track_record_is_skipped():
    conn = FakeConn()
    with patched(se, log=lambda msg: None):
        assert (se._sweep_house_asset(conn, "BTC", HISTORY), conn.writes) == ([], [])


# ---------- sweep_house: refetch across an outage gap ----------

def run_sweep(conn: FakeConn, window: list) -> tuple[int, list[int], list[str]]:
    """One sweep over a single asset; returns (events, crypto_hlc_since start args, logs)."""
    since_calls, logs = [], []

    def since(asset, start_ms):
        since_calls.append(start_ms)
        return [b for b in HISTORY if b[0] >= start_ms]

    with patched(se, crypto_hlc=lambda asset: window, crypto_hlc_since=since, log=logs.append), \
            patched(se.sr, ASSETS=("BTC",)):
        n = se.sweep_house(conn)
    return n, since_calls, logs


def test_gap_refetches_from_170_bars_before_the_last_processed_bar():
    conn = flat_through_167()
    _, since_calls, _ = run_sweep(conn, HISTORY[-(ENTRY_LB + 5):])
    assert since_calls == [T0 + (ENTRY_LB - 1) * H - (ENTRY_LB + 2) * H]


def test_gap_catch_up_replays_the_missed_entry_as_backfill():
    conn = flat_through_167()
    run_sweep(conn, HISTORY[-(ENTRY_LB + 5):])
    (kind, params), = signal_writes(conn)
    assert (kind, params[2], params[-2]) == ("INSERT", at(ENTRY_LB), False)


def test_gap_is_logged_as_a_warning():
    conn = flat_through_167()
    _, _, logs = run_sweep(conn, HISTORY[-(ENTRY_LB + 5):])
    assert any("WARNING gap" in m for m in logs)


def test_no_gap_uses_only_the_latest_window_and_writes_live():
    conn = flat_through_167()
    _, since_calls, _ = run_sweep(conn, HISTORY[:ENTRY_LB + 5])
    assert (since_calls, signal_writes(conn)[0][1][-2]) == ([], True)
