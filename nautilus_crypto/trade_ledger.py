"""Writes Nautilus position open/close events to quant.nautilus_trades (TimescaleDB), which
the dashboard reads via api.nautilus_trades. Plain helper (not an Actor) — strategies call it
from on_position_opened / on_position_changed / on_position_closed, because position events
route to the owning strategy.

Connection: TIMESCALE_URL env (sops-provided). All DB errors are swallowed + logged — a DB
hiccup must NEVER break trading. Disabled (no-op) if TIMESCALE_URL is unset (e.g. backtest).

One open row per (trader_id, position_id): a node restart re-opens the position with a new
ts_opened, so record_open closes older unclosed incarnations as exit_reason='superseded', and
record_close only ever touches the still-open row.
"""

from __future__ import annotations

import os

from nautilus_trader.model.enums import PositionSide


class TradeLedger:
    def __init__(
        self,
        environment: str | None = None,
        logger=None,
        asset_class: str | None = None,
    ):
        self._url = os.environ.get("TIMESCALE_URL")
        self._env = environment or os.environ.get("NAUTILUS_ENV", "testnet")
        # 'crypto' | 'equity' — segregates the two engines in quant.nautilus_trades.
        # Defaults to crypto so existing crypto callers (Accumulator/Donchian) are unchanged.
        self._asset_class = asset_class or os.environ.get("NAUTILUS_ASSET_CLASS", "crypto")
        self._log = logger
        self._conn = None

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def _cursor(self):
        import psycopg2  # imported lazily so backtests don't need it

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._url)
            self._conn.autocommit = True
        return self._conn.cursor()

    def _warn(self, msg):
        if self._log:
            self._log.warning(msg)

    @staticmethod
    def _is_backtest(e) -> bool:
        # BacktestEngine's default trader_id is BACKTESTER-xxx. Never let a backtest run
        # (e.g. backtest_stats.py invoked under a sops env that exposes TIMESCALE_URL) pollute
        # the LIVE execution table — the dashboard /nautilus reads it.
        return "BACKTEST" in str(getattr(e, "trader_id", "")).upper()

    def record_open(self, e) -> None:
        if not self.enabled or self._is_backtest(e):
            return
        try:
            iid = str(e.instrument_id)
            tid, pid, ts_opened = str(e.trader_id), str(e.position_id), int(e.ts_opened)
            with self._cursor() as cur:
                # A node restart re-opens the same position_id with a new ts_opened, so the
                # older incarnation would stay "open" forever. Close it out as superseded at the
                # new open time. Strict `<` keeps on_position_changed (same ts_opened) from
                # superseding its own row.
                cur.execute(
                    """
                    UPDATE quant.nautilus_trades
                       SET close_date = to_timestamp(%s/1e9), exit_reason = 'superseded',
                           synced_at = now()
                     WHERE trader_id = %s AND position_id = %s AND close_date IS NULL
                       AND open_date < to_timestamp(%s/1e9)
                    """,
                    (ts_opened, tid, pid, ts_opened),
                )
                cur.execute(
                    """
                    INSERT INTO quant.nautilus_trades
                      (trader_id, position_id, strategy, instrument, venue, environment,
                       asset_class, is_short, open_date, open_rate, quantity)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s, to_timestamp(%s/1e9), %s, %s)
                    ON CONFLICT (trader_id, position_id, open_date) DO UPDATE
                      SET quantity = EXCLUDED.quantity, open_rate = EXCLUDED.open_rate,
                          synced_at = now()
                    """,
                    (tid, pid, str(e.strategy_id), iid,
                     iid.split(".")[-1], self._env, self._asset_class,
                     e.side == PositionSide.SHORT,
                     ts_opened, float(e.avg_px_open), float(e.quantity)),
                )
        except Exception as ex:  # never break trading on a DB error
            self._warn(f"TradeLedger.record_open failed: {ex!r}")

    def record_close(self, e) -> None:
        if not self.enabled or self._is_backtest(e):
            return
        try:
            with self._cursor() as cur:
                cur.execute(
                    """
                    UPDATE quant.nautilus_trades
                       SET close_date = to_timestamp(%s/1e9), close_rate = %s,
                           realized_pnl = %s, profit_pct = %s, exit_reason = %s, synced_at = now()
                     WHERE trader_id = %s AND position_id = %s AND close_date IS NULL
                    """,
                    (int(e.ts_closed), float(e.avg_px_close), float(e.realized_pnl),
                     float(e.realized_return), "signal", str(e.trader_id), str(e.position_id)),
                )
        except Exception as ex:
            self._warn(f"TradeLedger.record_close failed: {ex!r}")
