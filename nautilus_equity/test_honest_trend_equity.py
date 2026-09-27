"""Integration tests for the event-driven HonestTrendEquity port.

These run the real NautilusTrader BacktestEngine on crafted data to verify the ported
behaviour: entries fire on the trend setup, the exchange-side protective stop fills on a
gap-down, and the regime gate can veto entries.
"""

from __future__ import annotations

import math

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from honest_trend_equity import HonestTrendEquity, HonestTrendEquityConfig
from crypto_data import bars_from_frame  # noqa: E402  (pandas-3-safe bar builder)


def _bars_from_closes(closes, vols=None):
    n = len(closes)
    idx = pd.date_range("2023-01-02", periods=n, freq="B", tz="UTC")
    rows = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) * 1.003
        lo = min(o, c) * 0.997
        # Gently rising volume so it stays above its trailing SMA — keeps the
        # `volume > vol_sma` entry filter deterministically satisfied for these tests
        # (we exercise entry/stop mechanics here, not the volume filter's selectivity).
        v = vols[i] if vols else 1_000_000 * (1.0 + 0.03 * i)
        rows.append((o, hi, lo, c, v))
        prev = c
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


def _run(df, **cfg):
    # bypass_logging=True is REQUIRED here: the Rust logging subsystem initializes once
    # per process and aborts on a second BacktestEngine, which pytest hits by running
    # multiple engine tests in one process. Bypassing it makes the engine re-creatable.
    engine = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    instrument = TestInstrumentProvider.equity(symbol="NVDA", venue="NASDAQ")
    venue = Venue("NASDAQ")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(100_000, USD)],
        base_currency=USD,
    )
    engine.add_instrument(instrument)
    bar_type = BarType.from_str(f"{instrument.id}-1-DAY-LAST-EXTERNAL")
    bars = bars_from_frame(df, bar_type, instrument)
    engine.add_data(bars)
    base = dict(instrument_id=str(instrument.id), bar_type=bar_type)
    base.update(cfg)
    strat = HonestTrendEquity(HonestTrendEquityConfig(**base))
    engine.add_strategy(strat)
    engine.run()
    final = float(engine.portfolio.account(venue).balance_total(USD))
    engine.dispose()
    return strat, final


def _entry_then_crash_closes():
    """Decline (warmup) → sustained rise (cross-up entry) → crash (stop-out)."""
    closes = []
    closes += [100 - i * 0.4 for i in range(35)]  # 0-34: decline to ~86, fast<slow
    closes += [86 + i * 1.6 for i in range(25)]   # 35-59: rise to ~124, cross-up + trend
    closes += [124 - i * 6.0 for i in range(8)]   # 60-67: crash ~124→76 (-39%), breach -5%
    closes += [76 for _ in range(5)]              # 68-72: settle (bars for stop detection)
    return closes


def test_smoke_entries_and_fills():
    closes = _entry_then_crash_closes()
    strat, _ = _run(
        _bars_from_closes(closes),
        ema_fast=10, ema_slow=30, adx_period=14, adx_threshold=8.0,
        vol_window=5, min_hold_bars=2, stop_loss_pct=0.05,
    )
    assert strat.entries >= 1, f"expected an entry, got {strat.entries}"
    assert strat.stops_placed >= 1


def test_protective_stop_fills_on_gap_down():
    closes = _entry_then_crash_closes()
    strat, _ = _run(
        _bars_from_closes(closes),
        ema_fast=10, ema_slow=30, adx_period=14, adx_threshold=8.0,
        vol_window=5, min_hold_bars=2, stop_loss_pct=0.05,
    )
    # The -5% exchange-side stop must catch the crash (not a soft next-bar exit).
    assert strat.stop_exits >= 1, (
        f"stop did not fire: entries={strat.entries} stops_placed={strat.stops_placed} "
        f"stop_exits={strat.stop_exits} ema_exits={strat.exits}"
    )


def test_regime_gate_blocks_all_entries(tmp_path):
    closes = _entry_then_crash_closes()
    # CSV that marks every relevant date as extreme greed → block_above 80 vetoes entries.
    idx = pd.date_range("2023-01-02", periods=len(closes), freq="B", tz="UTC")
    csv = tmp_path / "regime.csv"
    csv.write_text("date,value\n" + "\n".join(f"{d.strftime('%Y-%m-%d')},95" for d in idx))
    strat, _ = _run(
        _bars_from_closes(closes),
        ema_fast=10, ema_slow=30, adx_period=14, adx_threshold=8.0,
        vol_window=5, min_hold_bars=2, stop_loss_pct=0.05,
        regime_csv=str(csv), regime_threshold=80.0, regime_mode="block_above",
    )
    assert strat.entries == 0, f"regime gate should have blocked all entries, got {strat.entries}"
