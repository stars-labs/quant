"""Integration test: drive SignalAlerter through a real BacktestEngine.

The pure detectors are covered by test_signal_detect.py. This test exercises the part that
unit tests can't — the Nautilus subscribe → dispatch → on_bar wiring — because that exact gap
(a live-only code path never hit by backtests) is what crashed the first testnet deploy.

Feeds a synthetic 1-minute bar path containing a known spike and a known dip, with a recording
notifier, and asserts the actor actually emitted both alerts. Requires nautilus_trader.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signal_alerter import SignalAlerter  # noqa: E402


class _RecordingNotifier:
    """Stand-in for TelegramNotifier — captures messages instead of hitting the network."""

    enabled = True

    def __init__(self):
        self.sent: list[str] = []

    def send(self, text: str, markdown: bool = True) -> bool:
        self.sent.append(text)
        return True


def _bar(bar_type, px: float, ts_ns: int) -> Bar:
    p = Price(px, 2)
    # tiny hi/lo envelope so OHLC is valid regardless of direction
    hi = Price(px * 1.001, 2)
    lo = Price(px * 0.999, 2)
    return Bar(bar_type, p, hi, lo, p, Quantity(1, 6), ts_ns, ts_ns)


def _build_path(bar_type) -> list[Bar]:
    """5 flat minutes @100, then +2% (spike PUMP), then -3.9% in 1m (dip FLASH)."""
    minute = 60_000_000_000
    prices = [100.0, 100.0, 100.0, 100.0, 100.0, 102.0, 98.0]
    return [_bar(bar_type, px, i * minute) for i, px in enumerate(prices)]


def _run():
    engine = BacktestEngine(
        config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True))
    )
    instrument = TestInstrumentProvider.btcusdt_binance()
    venue = Venue("BINANCE")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(1_000_000, USDT)],
        base_currency=None,
    )
    engine.add_instrument(instrument)
    bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-LAST-EXTERNAL")
    engine.add_data(_build_path(bar_type))

    notifier = _RecordingNotifier()
    alerter = SignalAlerter(
        [instrument], bar_spec="1-MINUTE-LAST-EXTERNAL", notifier=notifier
    )
    engine.add_actor(alerter)
    engine.run()
    engine.dispose()
    return notifier.sent


def test_alerter_emits_spike_and_dip_through_engine():
    sent = _run()
    assert any("PUMP" in m for m in sent), f"expected a spike alert, got: {sent}"
    assert any("Accumulation dip" in m for m in sent), f"expected a dip alert, got: {sent}"


if __name__ == "__main__":
    msgs = _run()
    print(f"alerter emitted {len(msgs)} message(s):")
    for m in msgs:
        print("  ---")
        print("  " + m.replace("\n", "\n  "))
    ok = any("PUMP" in m for m in msgs) and any("Accumulation dip" in m for m in msgs)
    print("\nRESULT:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
