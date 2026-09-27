"""HonestTrendEquity backtest for ANY US stock/ETF on real financialdata.net daily bars.

The IB-catalog path (grid_honest_equity_real.run_one) covers NVDA/AMD/QQQ with hourly+
daily bars; this module extends the playground to any US ticker using daily OHLCV from
findata.py (10y history, cached, budget-guarded). Same real Nautilus engine, same
HonestTrendEquity strategy, same metric definitions as run_one (daily realized-cash
equity curve; Sharpe annualized at 252; Calmar = CAGR/|maxDD|).

Used by backtest_runner.run_honest_trend for assets outside the IB catalog trio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "strategies")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from grid_honest_equity_real import _max_drawdown, _sharpe  # noqa: E402  (same metric defs)
from honest_trend_equity import HonestTrendEquity, HonestTrendEquityConfig  # noqa: E402
from crypto_data import bars_from_frame  # noqa: E402  (pandas-3-safe bar builder)

_START_BALANCE = 100_000
_VIX_CSV = _HERE.parent / "data" / "vix_history.csv"


def run_any(symbol: str, ema_fast: int, ema_slow: int, since_years: float | None = None) -> dict:
    """Daily-bar HonestTrend backtest for an arbitrary US symbol. Raises ValueError on
    missing/short data (the runner surfaces the message to the user)."""
    import findata

    if symbol in findata.COMMODITIES:
        rows = findata.ohlcv_commodity(symbol, min_bars=2600)
    else:
        rows = findata.ohlcv_us(symbol, min_bars=2600)
    if not rows:
        raise ValueError(f"no daily data for {symbol!r} (unknown symbol or data budget exhausted — try again tomorrow)")
    if len(rows) < ema_slow + 50:
        raise ValueError(f"{symbol}: only {len(rows)} daily bars — need at least ema_slow+50 ({ema_slow + 50})")

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]].astype(float)
    # Sanitize OHLC consistency — the commodity feed occasionally ships high < close etc.,
    # which Nautilus (correctly) rejects. Clamp to the row's true extremes.
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    df["volume"] = df["volume"].clip(lower=0)
    if since_years:
        # Trailing N-year window anchored to the last bar.
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=since_years * 365.25)]
        if len(df) < ema_slow + 50:
            raise ValueError(f"{symbol}: window too short for ema_slow={ema_slow} — pick a longer 数据周期")

    instrument = TestInstrumentProvider.equity(symbol=symbol, venue="NASDAQ")
    engine = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    venue = Venue("NASDAQ")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(_START_BALANCE, USD)],
        base_currency=USD,
    )
    engine.add_instrument(instrument)
    bar_type = BarType.from_str(f"{instrument.id}-1-DAY-LAST-EXTERNAL")
    engine.add_data(bars_from_frame(df, bar_type, instrument))

    strategy = HonestTrendEquity(
        HonestTrendEquityConfig(
            instrument_id=str(instrument.id),
            bar_type=bar_type,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            adx_period=14,
            adx_threshold=18.0,
            vol_window=20,
            min_hold_bars=1,
            stop_loss_pct=0.08,
            rth_only=False,
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
    acc = engine.trader.generate_account_report(venue)
    bal_by_day: dict = {}
    for ts, total in zip(acc.index, acc["total"].astype(float)):
        bal_by_day[ts.date()] = total
    curve = [_START_BALANCE] + [bal_by_day[d] for d in sorted(bal_by_day)]
    rets = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve)) if curve[i - 1] > 0]
    mdd = _max_drawdown(curve)
    sharpe = _sharpe(rets, 252)
    ret_total = final / _START_BALANCE - 1
    days = max(1, (sorted(bal_by_day)[-1] - sorted(bal_by_day)[0]).days) if bal_by_day else 1
    years = max(days / 365.25, 1e-9)
    cagr = (final / _START_BALANCE) ** (1 / years) - 1 if final > 0 else -1.0
    calmar = cagr / mdd if mdd > 0 else float("inf")

    result = {
        "symbol": symbol,
        "bars": len(df),
        "entries": strategy.entries,
        "pyramids": strategy.pyramids,
        "exits": strategy.exits,
        "stops": strategy.stop_exits,
        "fills": len(fills),
        "final": final,
        "ret_pct": ret_total * 100,
        "mdd_pct": mdd * 100,
        "sharpe": sharpe,
        "calmar": calmar,
        "curve": curve,
        "period": f"{df.index[0].date()} → {df.index[-1].date()}",
        "period_start": str(df.index[0].date()),
        "period_end": str(df.index[-1].date()),
    }
    engine.dispose()
    return result
