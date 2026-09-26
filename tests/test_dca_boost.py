"""Tests for strategies/dca_boost.py — must mirror nautilus_crypto/accumulator.py.

Run: P=nautilus_equity/.venv/bin/python; $P -c "import sys; sys.path.insert(0,'tests'); import test_dca_boost as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

import dca_boost as b  # noqa: E402

FULL = [100.0] * 30


def test_plain_day():
    assert b.units(50, 95.0, FULL)["units"] == 1.0


def test_fear_adds_three():
    u = b.units(25, 95.0, FULL)
    assert u["units"] == 4.0 and u["fear_add"] == 3.0


def test_deep_fear_adds_five_not_eight():
    u = b.units(15, 95.0, FULL)
    assert u["units"] == 6.0 and u["fear_add"] == 5.0


def test_dip_stacks_with_fear():
    u = b.units(10, 80.0, FULL)
    assert u["units"] == 8.0 and u["dip_add"] == 2.0 and abs(u["drawdown"] + 0.2) < 1e-12


def test_dip_needs_full_window():
    u = b.units(50, 50.0, [100.0] * 29)
    assert u["units"] == 1.0 and u["drawdown"] is None


def test_window_includes_current_bar_high():
    # current bar's own high is part of the window (Accumulator appends before deciding)
    u = b.units(50, 80.0, [90.0] * 29 + [100.0])
    assert u["dip_add"] == 2.0


def test_simulate_skips_warmup_days():
    days = [(f"2025-12-{d:02d}", 50, 100.0, 100.0) for d in range(1, 31)]
    days += [("2026-01-01", 10, 100.0, 50.0), ("2026-01-02", 50, 100.0, 100.0)]
    s = b.simulate(days, "2026-01-01")
    assert s["days"] == 2 and s["boosted_days"] == 1
    # plain: $1@50 + $1@100 → 2/0.03 = 66.67; smart: $8@50 + $1@100 → 9/0.17 = 52.94
    assert abs(s["plain_cost"] - 2 / 0.03) < 1e-9
    assert abs(s["smart_cost"] - 9 / 0.17) < 1e-9
    assert s["cost_diff"] < 0


def test_simulate_empty():
    assert b.simulate([("2025-12-01", 50, 1.0, 1.0)], "2026-01-01") is None
