"""Unit tests for strategies.strategy_record (house Donchian 168/72 replay).

Plain test_* functions with bare asserts — runs under pytest or the stdlib harness:
  P=nautilus_equity/.venv/bin/python
  $P -c "import sys; sys.path.insert(0,'tests'); import test_strategy_record as t; \
[getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Strategy modules live in strategies/ at the repo root and have no __init__.py.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "strategies"))

from strategy_record import (  # noqa: E402
    ENTRY_LB,
    EXIT_LB,
    channels,
    net_return,
    step,
)

H = 3_600_000  # one hour in ms
T0 = 1_767_225_599_999  # 2025-12-31 23:59:59.999 UTC — a Binance 1h close_time


def flat(n: int, start: int = 0, high: float = 100.0, low: float = 90.0, close: float = 95.0):
    """n identical bars (the channel is then exactly [low, high])."""
    return [(T0 + (start + k) * H, high, low, close) for k in range(n)]


def bar(idx: int, high: float, low: float, close: float):
    return (T0 + idx * H, high, low, close)


def warmup():
    return flat(ENTRY_LB)


def test_entry_on_close_above_prior_high():
    bars = warmup() + [bar(ENTRY_LB, 102, 94, 101)]
    assert step(bars, None, after_ms=0) == [
        {"type": "entry", "ts": T0 + ENTRY_LB * H, "price": 101, "level": 100.0}
    ]


def test_close_equal_to_channel_is_not_a_breakout():
    bars = warmup() + [bar(ENTRY_LB, 101, 94, 100.0)]
    assert step(bars, None, after_ms=0) == []


def test_exit_on_close_below_prior_low_when_long():
    bars = warmup() + [bar(ENTRY_LB, 95, 85, 89)]
    pos = {"entry_ts": T0 - H, "entry_price": 95.0}
    assert step(bars, pos, after_ms=0) == [
        {"type": "exit", "ts": T0 + ENTRY_LB * H, "price": 89, "level": 90.0}
    ]


def test_no_exit_while_flat():
    bars = warmup() + [bar(ENTRY_LB, 95, 85, 89)]
    assert step(bars, None, after_ms=0) == []


def test_no_reentry_while_long():
    # Two consecutive breakouts: only the first is an entry, the second is just "still long".
    bars = warmup() + [bar(ENTRY_LB, 102, 94, 101), bar(ENTRY_LB + 1, 110, 100, 109)]
    events = step(bars, None, after_ms=0)
    assert [e["type"] for e in events] == ["entry"]


def test_already_long_position_blocks_entry():
    bars = warmup() + [bar(ENTRY_LB, 102, 94, 101)]
    assert step(bars, {"entry_ts": T0, "entry_price": 95.0}, after_ms=0) == []


def test_reentry_after_exit():
    bars = warmup() + [
        bar(ENTRY_LB, 102, 94, 101),      # entry: > 100
        bar(ENTRY_LB + 1, 95, 85, 89),    # exit: < 90 (prior 72 lows)
        bar(ENTRY_LB + 2, 104, 88, 103),  # re-entry: > 102 (prior 168 highs)
    ]
    events = step(bars, None, after_ms=0)
    assert [(e["type"], e["price"], e["level"]) for e in events] == [
        ("entry", 101, 100.0),
        ("exit", 89, 90.0),
        ("entry", 103, 102),
    ]


def test_after_ms_skips_already_processed_bars():
    bars = warmup() + [bar(ENTRY_LB, 102, 94, 101), bar(ENTRY_LB + 1, 95, 85, 89)]
    # Entry bar already processed (after_ms == its close ts) and recorded as the position.
    pos = {"entry_ts": T0 + ENTRY_LB * H, "entry_price": 101.0}
    events = step(bars, pos, after_ms=T0 + ENTRY_LB * H)
    assert [(e["type"], e["ts"]) for e in events] == [("exit", T0 + (ENTRY_LB + 1) * H)]


def test_after_ms_beyond_last_bar_yields_nothing():
    bars = warmup() + [bar(ENTRY_LB, 102, 94, 101)]
    assert step(bars, None, after_ms=bars[-1][0]) == []


def test_current_bar_high_not_in_its_own_entry_lookback():
    # The bar's own high (200) is above its close; only the PRIOR 168 highs (100) count.
    bars = warmup() + [bar(ENTRY_LB, 200, 94, 150)]
    assert step(bars, None, after_ms=0)[0]["level"] == 100.0


def test_current_bar_low_not_in_its_own_exit_lookback():
    # The bar's own low (10) is below its close; only the PRIOR 72 lows (90) count.
    bars = warmup() + [bar(ENTRY_LB, 95, 10, 50)]
    events = step(bars, {"entry_ts": T0, "entry_price": 95.0}, after_ms=0)
    assert events == [{"type": "exit", "ts": T0 + ENTRY_LB * H, "price": 50, "level": 90.0}]


def test_exit_lookback_is_only_the_last_72_bars():
    # A deep low 73 bars back is outside the exit window, so it must not set the level.
    bars = flat(ENTRY_LB)
    bars[ENTRY_LB - EXIT_LB - 1] = (bars[ENTRY_LB - EXIT_LB - 1][0], 100, 50, 95)
    bars.append(bar(ENTRY_LB, 95, 85, 89))
    events = step(bars, {"entry_ts": T0, "entry_price": 95.0}, after_ms=0)
    assert events and events[0]["level"] == 90.0


def test_insufficient_lookback_yields_no_events():
    # 168 bars: the last one only has 167 prior bars → never evaluated, even on a breakout.
    bars = flat(ENTRY_LB - 1) + [bar(ENTRY_LB - 1, 300, 94, 250)]
    assert step(bars, None, after_ms=0) == []
    assert step([], None, after_ms=0) == []


def test_first_bar_with_full_lookback_is_evaluated():
    bars = flat(ENTRY_LB) + [bar(ENTRY_LB, 300, 94, 250)]
    assert len(step(bars, None, after_ms=0)) == 1


def test_channels_for_next_bar_include_last_bar():
    bars = flat(ENTRY_LB) + [bar(ENTRY_LB, 120, 80, 115)]
    ch = channels(bars)
    assert ch == {
        "last_ts": T0 + ENTRY_LB * H,
        "last_close": 115,
        "channel_high": 120,
        "channel_low": 80,
    }


def test_channels_use_their_own_lookbacks():
    bars = flat(ENTRY_LB + 10)
    bars[-ENTRY_LB] = (bars[-ENTRY_LB][0], 130, 90, 95)             # oldest bar of the entry window
    bars[-ENTRY_LB - 1] = (bars[-ENTRY_LB - 1][0], 999, 1, 95)       # just outside both windows
    bars[-EXIT_LB - 1] = (bars[-EXIT_LB - 1][0], 100, 70, 95)        # just outside the exit window
    ch = channels(bars)
    assert (ch["channel_high"], ch["channel_low"]) == (130, 90.0)


def test_channels_none_without_full_lookback():
    ch = channels(flat(EXIT_LB))
    assert ch["channel_high"] is None and ch["channel_low"] == 90.0


def test_channels_require_a_bar():
    try:
        channels([])
    except ValueError:
        return
    raise AssertionError("channels([]) should raise ValueError")


def test_net_return_charges_fee_both_sides():
    assert abs(net_return(100.0, 110.0) - (1.1 * 0.999 * 0.999 - 1)) < 1e-12
    assert net_return(100.0, 100.0) < 0  # flat round trip loses the fees
