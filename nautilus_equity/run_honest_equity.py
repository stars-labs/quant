"""Stage 2 runner — backtest the event-driven HonestTrendEquity port.

Uses synthetic data by default (no IB needed) to prove the ported logic executes and
trades. Swap in a ParquetDataCatalog (from download_ib.py) for real adjusted bars.

Run:  nautilus_equity/.venv/bin/python nautilus_equity/run_honest_equity.py
"""

from __future__ import annotations

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from pathlib import Path

from backtest_spike import synthetic_daily_bars
from honest_trend_equity import HonestTrendEquity, HonestTrendEquityConfig
from crypto_data import bars_from_frame  # noqa: E402  (pandas-3-safe bar builder)

_VIX_CSV = Path(__file__).resolve().parent.parent / "data" / "vix_history.csv"


def main() -> int:
    engine = BacktestEngine(
        config=BacktestEngineConfig(logging=LoggingConfig(log_level="ERROR")),
    )

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
    df = synthetic_daily_bars(n=600)
    bars = bars_from_frame(df, bar_type, instrument)
    engine.add_data(bars)

    # Shorter EMAs on synthetic data so the cross actually fires; the production
    # equity config will use the tuned 72/144 trend lengths.
    strategy = HonestTrendEquity(
        HonestTrendEquityConfig(
            instrument_id=str(instrument.id),
            bar_type=bar_type,
            ema_fast=10,
            ema_slow=30,
            adx_period=14,
            adx_threshold=15.0,
            vol_window=20,
            min_hold_bars=2,
            stop_loss_pct=0.05,  # Stage 3: exchange-side protective stop at -5% from avg
            rth_only=False,  # synthetic daily bars have no intraday clock
            # FNG→VIX: avoid opening new trend longs in a high-volatility panic regime.
            regime_csv=str(_VIX_CSV) if _VIX_CSV.exists() else None,
            regime_threshold=30.0,
            regime_mode="block_above",
        )
    )
    engine.add_strategy(strategy)

    engine.run()

    account = engine.portfolio.account(venue)
    final = float(account.balance_total(USD))
    fills = engine.trader.generate_order_fills_report()
    print("=" * 56)
    print(f"  strategy        : HonestTrendEquity (event-driven port)")
    print(f"  instrument      : {instrument.id}")
    print(f"  bars            : {len(bars)}")
    print(f"  entries         : {strategy.entries}")
    print(f"  pyramids        : {strategy.pyramids}")
    print(f"  ema-cross exits : {strategy.exits}")
    print(f"  stops placed    : {strategy.stops_placed}")
    print(f"  stop-out exits  : {strategy.stop_exits}")
    print(f"  order fills     : {len(fills)}")
    print(f"  final equity    : ${final:,.2f}  ({(final/100_000 - 1)*100:+.2f}%)")
    print("=" * 56)

    engine.dispose()
    return 0 if len(fills) >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
