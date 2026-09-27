"""Tests for the equity/commodity opportunity radar (migration 036): strategies/market_scan.py
metrics and signal_evaluator.market_rows' universe + sources. No DB, no network.

Run: .venv-bots/bin/python -c "import sys; sys.path.insert(0,'tests'); import test_market_scan as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

import market_scan as ms  # noqa: E402
import signal_evaluator as se  # noqa: E402

DAY = 86_400_000


def bars(closes: list[float]) -> list[tuple[int, float]]:
    return [(i * DAY, c) for i, c in enumerate(closes)]


def close_to(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def test_metrics_need_a_full_52_week_window():
    assert ms.metrics(bars([100.0] * (ms.HIGH_LB - 1))) is None
    assert ms.metrics(bars([100.0] * ms.HIGH_LB)) is not None


def test_metrics_at_a_new_high_read_zero_from_it():
    m = ms.metrics(bars([float(i) for i in range(1, 301)]))
    assert m["last_close"] == 300.0 and m["high_52w"] == 300.0 and m["from_high_52w"] == 0.0
    assert m["low_52w"] == 49.0                                  # the last 252 closes: 49..300
    assert close_to(m["ma200"], sum(range(101, 301)) / 200)
    assert close_to(m["ret_1m"], 300 / 279 - 1)
    assert m["last_ts"] == 299 * DAY
    assert ms.is_near_high(m) and not ms.is_deep(m)


def test_metrics_drawdown_and_trend_below_the_average():
    closes = [100.0] * 100 + [200.0] * 100 + [120.0] * 100
    m = ms.metrics(bars(closes))
    assert close_to(m["from_high_52w"], -0.4)
    assert close_to(m["vs_ma200"], 120 / 160 - 1)
    assert ms.is_deep(m) and not ms.is_near_high(m)


def test_a_high_older_than_52_weeks_is_forgotten():
    m = ms.metrics(bars([500.0] + [100.0] * ms.HIGH_LB))
    assert m["high_52w"] == 100.0 and m["from_high_52w"] == 0.0


def test_non_positive_closes_are_rejected():
    # Continuous futures printed a negative close once (WTI, April 2020): no ratio is meaningful.
    assert ms.metrics(bars([50.0] * 300 + [-1.0])) is None


def test_thresholds_are_inclusive():
    assert ms.is_near_high({"from_high_52w": ms.NEAR_HIGH})
    assert ms.is_deep({"from_high_52w": ms.DEEP_DD})
    assert not ms.is_near_high({"from_high_52w": None}) and not ms.is_deep({})


def test_breadth_counts_only_rows_with_an_average():
    rows = [{"vs_ma200": 0.1}, {"vs_ma200": -0.2}, {"vs_ma200": 0.0}, {"vs_ma200": None}]
    assert ms.breadth(rows) == (1, 3)


def test_equity_universe_is_core_then_semis_without_duplicates():
    u = se.equity_scan_universe([("NVDA", "NVIDIA"), ("MU", "Micron"), ("AMD", "AMD")])
    syms = [r[0] for r in u]
    assert syms[:len(ms.EQUITY_CORE)] == [r[0] for r in ms.EQUITY_CORE]
    assert syms.count("NVDA") == 1 and syms[-2:] == ["AMD", "MU"]
    assert u[-1] == ("MU", "semis", None, "Micron")          # zh falls back to the ticker


class FakeConn:
    def __init__(self, snaps, semis):
        self.results = [snaps, semis]

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                pass

            def fetchall(self):
                return conn.results.pop(0)

        return Cur()


def test_market_rows_read_commodities_from_snapshots_and_equities_from_yahoo():
    rising = [[i * DAY, float(i + 1)] for i in range(400)]
    snaps = [("GC", {"kind": "commodity", "zh": "黄金", "en": "Gold", "closes": rising}),
             ("ZZ", {"kind": "commodity", "zh": "短", "en": "Short", "closes": rising[:10]})]
    fetched = []

    def closes_yahoo(sym):
        fetched.append(sym)
        return [] if sym == "SPY" else [(t, c) for t, c in rising]

    fake = types.ModuleType("findata")
    fake.closes_yahoo = closes_yahoo
    real, logs = sys.modules.get("findata"), []
    sys.modules["findata"] = fake
    orig_log, se.log = se.log, logs.append
    try:
        rows = se.market_rows(FakeConn(snaps, [("MU", "Micron")]))
    finally:
        se.log = orig_log
        if real is None:
            del sys.modules["findata"]
        else:
            sys.modules["findata"] = real
    by = {(r[0], r[1]): r for r in rows}
    assert by[("commodity", "GC")][2:5] == ("metals", "黄金", "Gold")
    assert ("commodity", "ZZ") not in by                      # too short: no row, no crash
    assert ("equity", "SPY") not in by and any("SPY" in m for m in logs)
    assert by[("equity", "MU")][2:5] == ("semis", None, "Micron")
    assert fetched == [r[0] for r in ms.EQUITY_CORE] + ["MU"]  # one call per ticker, none for commodities
