"""Stage 1 spike — prove the NautilusTrader engine runs end-to-end on a US-equity
instrument with synthetic data (no IB connection required).

This deliberately mirrors the freqtrade → Nautilus concept mapping so the migration
cost is visible up front:

  freqtrade populate_indicators (vectorized pandas)  ->  incremental EMA updated on_bar
  freqtrade custom_stake_amount (Kelly)              ->  kelly_stake() reused UNCHANGED
  freqtrade Backtesting class                        ->  BacktestEngine

Run:  nautilus_equity/.venv/bin/python nautilus_equity/backtest_spike.py
"""

from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

# Reuse the existing, framework-agnostic Kelly sizer from the freqtrade strategies
# dir verbatim — this is the whole point of the "reuse unchanged" migration claim.
_STRATS = Path(__file__).resolve().parent.parent / "strategies"
sys.path.insert(0, str(_STRATS))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nautilus_crypto"))
from crypto_data import bars_from_frame  # noqa: E402  (pandas-3-safe bar builder)
from kelly_sizer import kelly_stake  # noqa: E402

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig  # noqa: E402
from nautilus_trader.config import LoggingConfig, StrategyConfig  # noqa: E402
from nautilus_trader.indicators import ExponentialMovingAverage  # noqa: E402
from nautilus_trader.model.currencies import USD  # noqa: E402
from nautilus_trader.model.data import Bar, BarType  # noqa: E402
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide  # noqa: E402
from nautilus_trader.model.identifiers import Venue  # noqa: E402
from nautilus_trader.model.objects import Money  # noqa: E402
from nautilus_trader.test_kit.providers import TestInstrumentProvider  # noqa: E402
from nautilus_trader.trading.strategy import Strategy  # noqa: E402


def synthetic_daily_bars(n: int = 400, start_price: float = 100.0) -> pd.DataFrame:
    """Deterministic trending+oscillating OHLCV so the EMA cross actually fires.

    No randomness — reproducible runs. drift gives a slow uptrend; the sine wave
    forces enough crossovers to exercise both entry and exit paths.
    """
    idx = pd.date_range("2023-01-02", periods=n, freq="B", tz="UTC")  # business days
    rows = []
    price = start_price
    for i in range(n):
        drift = 0.03 * i
        wave = 8.0 * math.sin(i / 11.0)
        close = start_price + drift + wave
        open_ = price
        high = max(open_, close) * 1.004
        low = min(open_, close) * 0.996
        # Vary volume so the `volume > volume_sma` entry filter can actually trigger;
        # constant volume would equal its own SMA and block every entry.
        vol = 1_000_000 * (1.0 + 0.6 * math.sin(i / 7.0))
        rows.append((open_, high, low, close, vol))
        price = close
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])
    return df


class EmaCrossEquityConfig(StrategyConfig, frozen=True):
    bar_type: BarType
    instrument_id: str
    fast_period: int = 10
    slow_period: int = 30
    risk_frac: float = 0.10  # proposed fraction of equity per entry (pre-Kelly)


class EmaCrossEquity(Strategy):
    """Event-driven EMA cross with the Kelly sizer wired into the entry path.

    stats=None here (no backtest-derived KellyStats yet), so kelly_stake falls back
    to the proposed stake — exactly the freqtrade behaviour when n < MIN_TRADES.
    Stage 2 will feed real KellyStats in.
    """

    def __init__(self, config: EmaCrossEquityConfig):
        super().__init__(config)
        self.fast = ExponentialMovingAverage(config.fast_period)
        self.slow = ExponentialMovingAverage(config.slow_period)
        self._kelly_stats = None  # Stage 2 populates this from a backtest zip
        self.entries = 0
        self.exits = 0

    def on_start(self):
        self.register_indicator_for_bars(self.config.bar_type, self.fast)
        self.register_indicator_for_bars(self.config.bar_type, self.slow)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar):
        if not self.indicators_initialized():
            return
        iid = self.instrument_id_from_config()
        instrument = self.cache.instrument(iid)
        if instrument is None:
            return

        if self.fast.value >= self.slow.value:
            if self.portfolio.is_flat(iid):
                self._enter_long(bar, instrument)
        elif self.fast.value < self.slow.value:
            if self.portfolio.is_net_long(iid):
                self.close_all_positions(iid)
                self.exits += 1

    def _enter_long(self, bar: Bar, instrument):
        account = self.portfolio.account(instrument.venue)
        equity_usd = float(account.balance_total(USD)) if account else 0.0
        if equity_usd <= 0:
            return
        # USD stake → share quantity. kelly_stake reused unchanged.
        stake_usd = kelly_stake(
            equity=equity_usd,
            stats=self._kelly_stats,
            proposed_stake=equity_usd * self.config.risk_frac,
            max_stake=equity_usd,
        )
        shares = int(stake_usd / float(bar.close))
        if shares < 1:
            return
        order = self.order_factory.market(
            instrument.id,
            OrderSide.BUY,
            instrument.make_qty(shares),
        )
        self.submit_order(order)
        self.entries += 1

    def instrument_id_from_config(self):
        from nautilus_trader.model.identifiers import InstrumentId

        return InstrumentId.from_str(self.config.instrument_id)

    def on_stop(self):
        self.close_all_positions(self.instrument_id_from_config())


def main() -> int:
    engine = BacktestEngine(
        config=BacktestEngineConfig(logging=LoggingConfig(log_level="ERROR")),
    )

    instrument = TestInstrumentProvider.equity(symbol="NVDA", venue="NASDAQ")
    venue = Venue("NASDAQ")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,  # equities = cash account, not margin
        starting_balances=[Money(100_000, USD)],
        base_currency=USD,
    )
    engine.add_instrument(instrument)

    bar_type = BarType.from_str(f"{instrument.id}-1-DAY-LAST-EXTERNAL")
    df = synthetic_daily_bars()
    bars = bars_from_frame(df, bar_type, instrument)
    engine.add_data(bars)

    strategy = EmaCrossEquity(
        EmaCrossEquityConfig(
            bar_type=bar_type,
            instrument_id=str(instrument.id),
        )
    )
    engine.add_strategy(strategy)

    engine.run()

    account = engine.portfolio.account(venue)
    final = float(account.balance_total(USD))
    fills = engine.trader.generate_order_fills_report()
    print("=" * 56)
    print(f"  instrument      : {instrument.id}")
    print(f"  bars            : {len(bars)}")
    print(f"  entries / exits : {strategy.entries} / {strategy.exits}")
    print(f"  order fills     : {len(fills)}")
    print(f"  starting equity : $100,000.00")
    print(f"  final equity    : ${final:,.2f}")
    print(f"  pnl             : ${final - 100_000:,.2f} ({(final/100_000 - 1)*100:+.2f}%)")
    print("=" * 56)

    engine.dispose()
    # Spike success = engine ran deterministically and produced at least one fill.
    return 0 if len(fills) >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
