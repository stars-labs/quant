"""Tests for ib_warmup.to_bars + HonestTrendEquity.preload (no IB connection needed).

Run: nautilus_equity/.venv/bin/python -c "import sys; sys.path.insert(0,'nautilus_equity'); import test_ib_warmup as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nautilus_trader.model.data import BarType  # noqa: E402

from honest_trend_equity import HonestTrendEquity, HonestTrendEquityConfig  # noqa: E402
from ib_warmup import HOUR_S, to_bars  # noqa: E402

BT = BarType.from_str("NVDA.NASDAQ-1-HOUR-LAST-EXTERNAL")
T0 = 1_790_000_000


def rows(n: int) -> list[tuple]:
    out = []
    for i in range(n):
        c = 100 + 10 * math.sin(i / 15) + i * 0.05
        out.append((T0 + i * HOUR_S, c - 0.3, c + 0.8, c - 0.9, c, 1_000.0))
    return out


def test_to_bars_stamps_the_bar_close():
    b = to_bars(rows(2), BT)
    assert len(b) == 2
    assert b[0].ts_event == (T0 + HOUR_S) * 1_000_000_000 == b[0].ts_init
    assert float(b[1].close) == round(rows(2)[1][4], 2)


def test_preload_warms_indicators_without_trading():
    s = HonestTrendEquity(HonestTrendEquityConfig(instrument_id="NVDA.NASDAQ", bar_type=BT,
                                                  log_bars=True))
    s.preload(to_bars(rows(10), BT))
    assert s._warm == (10, False)          # too few bars for EMA(100)
    s2 = HonestTrendEquity(HonestTrendEquityConfig(instrument_id="NVDA.NASDAQ", bar_type=BT,
                                                   log_bars=True))
    s2.preload(to_bars(rows(420), BT))     # what IB returns for 60 D × 1 hour RTH
    assert s2._warm[0] == 420 and s2._ready()
