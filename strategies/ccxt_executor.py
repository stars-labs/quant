"""Run the house strategies on exchanges Nautilus has no adapter for (Gate, HTX, …) via ccxt.

The house strategies need no exchange-side logic of their own — they are rules evaluated on
Binance mainnet data elsewhere:
  trend  — hold an asset exactly while quant.strategy_signals has an OPEN trade for it
           (written by signal_evaluator.py; the same signals users get and the Binance testnet
           Nautilus node mirrors). One fixed USDT notional per entry, sell everything on exit.
  dca    — once per UTC day buy DCA_BASE_USDT × the smart-DCA multiple of
           quant.dca_boost_days (dca_boost.py, mirror of the Nautilus accumulator) of BTC.
So execution is just "market buy / market sell on venue X" — ccxt's unified API does that for
100+ exchanges, no Nautilus fork or adapter needed.

Venues: EXEC_VENUES="gate:dry_run,htx:dry_run" — mode per venue:
  dry_run  public data only: fills are simulated at the live top of book with the venue's taker
           fee. Default on every venue (HTX has no testnet).
  testnet  ccxt sandbox (Gate has a spot testnet); needs <VENUE>_API_KEY / <VENUE>_API_SECRET.
  live     HTX funded spot only; requires EXEC_ALLOW_LIVE=1, an explicit funded month,
           HTX_SUBACCOUNT_UID / HTX_SPOT_ACCOUNT_ID and the durable order journal.
Ledger: quant.nautilus_trades rows (venue = GATE/HTX, environment = mode), trader_id
FOLLOW-<VENUE> (trend) / DCA-<VENUE> (dca) — /nautilus shows them; restarts resume from the
open rows. HTX live orders use executor_orders for restart-safe reconciliation.

Env: TIMESCALE_URL, EXEC_VENUES, TREND_NOTIONAL_USDT (500), DCA_BASE_USDT (100),
     EXEC_POLL_SECS (60), EXEC_ALLOW_LIVE, HTX_SUBACCOUNT_UID, HTX_SPOT_ACCOUNT_ID.
HTX live: per-entry20 USDT; funded monthly trend100 + DCA100, net trend proceeds recyclable.
Run: python strategies/ccxt_executor.py [--once]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import strategy_record as sr

HOUSE = sr.STRATEGY
MODES = ("dry_run", "testnet", "live")
DCA_ASSET = "BTC"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


# ---------------------------------------------------------------- pure decisions

def parse_venues(spec: str, allow_live: bool) -> list[tuple[str, str]]:
    """'gate:dry_run,htx:dry_run' → [('gate','dry_run'), ('htx','dry_run')]. Fails fast on an
    unknown mode, and on 'live' unless explicitly allowed (guardrail)."""
    out = []
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, mode = part.partition(":")
        mode = mode or "dry_run"
        if mode not in MODES:
            raise ValueError(f"EXEC_VENUES: unknown mode {mode!r} for {name!r} (use {MODES})")
        if mode == "live" and not allow_live:
            raise ValueError(f"EXEC_VENUES: {name}:live refused — set EXEC_ALLOW_LIVE=1 to trade "
                             "real money (crypto stays testnet/dry-run by default)")
        out.append((name.lower(), mode))
    return out


def trend_actions(open_signals: set[str] | None, held: dict[str, float],
                  assets: tuple[str, ...]) -> list[tuple[str, str]]:
    """[('buy'|'sell', asset)] that makes holdings match the public signals. None (the signal DB
    could not be read) → hold everything: never trade on missing information."""
    if open_signals is None:
        return []
    acts = []
    for a in assets:
        if a in open_signals and held.get(a, 0.0) <= 0:
            acts.append(("buy", a))
        elif a not in open_signals and held.get(a, 0.0) > 0:
            acts.append(("sell", a))
    return acts


def realized(entry_px: float, exit_px: float, qty: float, fee: float) -> tuple[float, float]:
    """(pnl in USDT, return) net of a taker fee on both legs."""
    gross = qty * (exit_px - entry_px)
    fees = qty * (entry_px + exit_px) * fee
    return gross - fees, (exit_px * (1 - fee)) / (entry_px * (1 + fee)) - 1


# ---------------------------------------------------------------- venue (ccxt)

@dataclass
class Fill:
    qty: float
    price: float


class Venue:
    """One exchange in one mode. dry_run touches only public endpoints."""

    def __init__(self, name: str, mode: str, ex=None):
        self.name, self.mode = name, mode
        self.label = name.upper()
        if ex is None:
            import ccxt
            cfg = {"enableRateLimit": True}
            if mode != "dry_run":
                cfg["apiKey"] = os.environ[f"{self.label}_API_KEY"]
                cfg["secret"] = os.environ[f"{self.label}_API_SECRET"]
            ex = getattr(ccxt, name)(cfg)
            if mode == "testnet":
                ex.set_sandbox_mode(True)
        self.ex = ex
        self.ex.load_markets()

    def symbol(self, asset: str) -> str:
        return f"{asset}/USDT"

    def taker_fee(self, asset: str) -> float:
        return float(self.ex.markets[self.symbol(asset)].get("taker") or 0.002)

    def _min_cost(self, asset: str) -> float:
        lim = self.ex.markets[self.symbol(asset)].get("limits") or {}
        return float((lim.get("cost") or {}).get("min") or 0.0)

    def buy(self, asset: str, notional: float) -> Fill | None:
        if self.mode == 'live':
            raise RuntimeError('Live orders require the funded HTX journal')
        sym = self.symbol(asset)
        if notional < self._min_cost(asset):
            log(f"{self.label} {asset}: {notional:.2f} USDT is below the minimum order")
            return None
        if self.mode == "dry_run":
            ask = float(self.ex.fetch_ticker(sym)["ask"])
            qty = float(self.ex.amount_to_precision(sym, notional / ask))
            return Fill(qty, ask) if qty > 0 else None
        free = float(self.ex.fetch_balance()["free"].get("USDT") or 0.0)
        cost = min(notional, free)
        if cost < self._min_cost(asset) or cost <= 0:
            log(f"{self.label} {asset}: free USDT {free:.2f} below the minimum order")
            return None
        order = self.ex.create_market_buy_order_with_cost(sym, cost)
        return self._filled(order)

    def sell(self, asset: str, qty: float) -> Fill | None:
        if self.mode == 'live':
            raise RuntimeError('Live orders require the funded HTX journal')
        sym = self.symbol(asset)
        if self.mode == "dry_run":
            bid = float(self.ex.fetch_ticker(sym)["bid"])
            return Fill(qty, bid)
        free = float(self.ex.fetch_balance()["free"].get(asset) or 0.0)
        amount = float(self.ex.amount_to_precision(sym, min(qty, free)))
        if amount <= 0:
            return None
        return self._filled(self.ex.create_market_sell_order(sym, amount))

    def _filled(self, order: dict) -> Fill | None:
        if not order.get("filled") or not order.get("average"):
            order = self.ex.fetch_order(order["id"], order["symbol"])
        qty, avg = float(order.get("filled") or 0), float(order.get("average") or 0)
        return Fill(qty, avg) if qty > 0 and avg > 0 else None


# ---------------------------------------------------------------- ledger (quant.nautilus_trades)

class Ledger:
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def ids(kind: str, venue: Venue, asset: str) -> tuple[str, str, str]:
        trader = f"{'FOLLOW' if kind == 'trend' else 'DCA'}-{venue.label}"
        strategy = f"{'SignalFollower' if kind == 'trend' else 'SmartDCA'}-{asset}"
        return trader, f"{asset}USDT.{venue.label}-{strategy}", strategy

    def open_rows(self, kind: str, venue: Venue) -> dict[str, tuple]:
        """asset → (open_date, open_rate, quantity, synced_at) of its open row."""
        trader = self.ids(kind, venue, "X")[0]
        with self.conn.cursor() as cur:
            cur.execute("""SELECT split_part(instrument, 'USDT', 1), open_date, open_rate, quantity,
                                  synced_at
                             FROM quant.nautilus_trades
                            WHERE trader_id = %s AND environment = %s
                              AND close_date IS NULL""", (trader, venue.mode))
            return {r[0]: (r[1], float(r[2]), float(r[3]), r[4]) for r in cur.fetchall()}

    def add(self, kind: str, venue: Venue, asset: str, fill: Fill, row: tuple | None) -> None:
        """Open a position, or (dca) grow the open one at the new average price."""
        trader, pid, strategy = self.ids(kind, venue, asset)
        with self.conn.cursor() as cur:
            if row is None:
                cur.execute(
                    """INSERT INTO quant.nautilus_trades
                         (trader_id, position_id, strategy, instrument, venue, environment,
                          asset_class, is_short, open_date, open_rate, quantity, synced_at)
                       VALUES (%s,%s,%s,%s,%s,%s,'crypto',false, now(), %s, %s, now())""",
                    (trader, pid, strategy, f"{asset}USDT.{venue.label}", venue.label, venue.mode,
                     fill.price, fill.qty))
            else:
                qty = row[2] + fill.qty
                avg = (row[1] * row[2] + fill.price * fill.qty) / qty
                cur.execute("""UPDATE quant.nautilus_trades SET open_rate = %s, quantity = %s,
                                      synced_at = now()
                                WHERE trader_id = %s AND position_id = %s
                                  AND environment = %s AND close_date IS NULL""",
                            (avg, qty, trader, pid, venue.mode))

    def close(self, kind: str, venue: Venue, asset: str, row: tuple, fill: Fill, fee: float) -> None:
        trader, pid, _ = self.ids(kind, venue, asset)
        pnl, ret = realized(row[1], fill.price, row[2], fee)
        with self.conn.cursor() as cur:
            cur.execute("""UPDATE quant.nautilus_trades
                              SET close_date = now(), close_rate = %s, realized_pnl = %s,
                                  profit_pct = %s, exit_reason = 'signal', synced_at = now()
                            WHERE trader_id = %s AND position_id = %s
                              AND environment = %s AND close_date IS NULL""",
                        (fill.price, pnl, ret, trader, pid, venue.mode))


# ---------------------------------------------------------------- strategies

def open_signals(conn) -> set[str] | None:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT asset FROM quant.strategy_signals "
                        "WHERE strategy = %s AND exit_ts IS NULL", (HOUSE,))
            return {r[0] for r in cur.fetchall()}
    except Exception as e:  # noqa: BLE001
        log(f"signal read failed — holding: {e!r}")
        return None


def run_trend(conn, venue: Venue, ledger: Ledger, notional: float) -> None:
    rows = ledger.open_rows("trend", venue)
    held = {a: r[2] for a, r in rows.items()}
    for side, asset in trend_actions(open_signals(conn), held, sr.ASSETS):
        try:
            if side == "buy":
                fill = venue.buy(asset, notional)
                if fill:
                    ledger.add("trend", venue, asset, fill, None)
                    log(f"{venue.label}/{venue.mode} trend BUY {asset} {fill.qty} @ {fill.price}")
            else:
                fill = venue.sell(asset, rows[asset][2])
                if fill:
                    ledger.close("trend", venue, asset, rows[asset], fill, venue.taker_fee(asset))
                    log(f"{venue.label}/{venue.mode} trend SELL {asset} {fill.qty} @ {fill.price}")
        except Exception as e:  # noqa: BLE001 — one asset must not stop the others
            log(f"{venue.label} trend {side} {asset} failed: {e!r}")


def run_dca(conn, venue: Venue, ledger: Ledger, base_usdt: float) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT day, units FROM quant.dca_boost_days ORDER BY day DESC LIMIT 1")
        today = cur.fetchone()
    if not today:
        return
    day, units = today[0], float(today[1])
    if day != datetime.now(timezone.utc).date():
        log(f"{venue.label} DCA: rule date {day} is not today UTC — holding")
        return
    row = ledger.open_rows("dca", venue).get(DCA_ASSET)
    if row is not None and row[3].astimezone(timezone.utc).date() >= day:
        return  # already bought for this FNG day
    fill = venue.buy(DCA_ASSET, base_usdt * units)
    if fill:
        ledger.add("dca", venue, DCA_ASSET, fill, row)
        log(f"{venue.label}/{venue.mode} DCA {day} ×{units:g} BUY {fill.qty} BTC @ {fill.price}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    dsn = os.environ.get("TIMESCALE_URL", "")
    if not dsn:
        print("TIMESCALE_URL required", file=sys.stderr)
        return 2
    venues = [Venue(n, m) for n, m in parse_venues(
        os.environ.get("EXEC_VENUES", "gate:dry_run,htx:dry_run"),
        os.environ.get("EXEC_ALLOW_LIVE") == "1")]
    if any(v.mode=='live' and v.name!='htx' for v in venues):
        raise ValueError('Live execution supports funded HTX spot only')
    notional = float(os.environ.get("TREND_NOTIONAL_USDT", "500"))
    dca_base = float(os.environ.get("DCA_BASE_USDT", "100"))
    poll = int(os.environ.get("EXEC_POLL_SECS", "60"))
    log("executor up: " + ", ".join(f"{v.label}:{v.mode}" for v in venues))

    import psycopg2
    conn = None
    live_runners = {}
    while True:
        try:
            if conn is None or conn.closed:
                conn = psycopg2.connect(dsn)
                conn.autocommit = True
                live_runners = {}
            ledger = Ledger(conn)
            for v in venues:
                if v.mode == 'live':
                    healthy, detail = False, 'initializing'
                    try:
                        if v.name not in live_runners:
                            from htx_live import LiveHTX
                            live_runners[v.name] = LiveHTX(v,conn,log)
                        live_runners[v.name].tick()
                        healthy = not live_runners[v.name].store.pending()
                        detail = 'ok' if healthy else 'unfinished order'
                    except Exception as e:
                        # Signed exchange URLs may contain credentials; log types only.
                        log(f'{v.label}/live paused: {type(e).__name__}')
                        detail = type(e).__name__
                    with conn.cursor() as cur:
                        cur.execute("INSERT INTO quant.executor_status (venue,healthy,detail) "
                                    "VALUES (%s,%s,%s) ON CONFLICT (venue) DO UPDATE SET "
                                    "checked_at=now(),healthy=EXCLUDED.healthy,detail=EXCLUDED.detail",
                                    (v.label,healthy,detail))
                    continue
                for job, arg in ((run_trend, notional), (run_dca, dca_base)):
                    try:
                        job(conn, v, ledger, arg)
                    except Exception as e:  # noqa: BLE001
                        log(f"{v.label} {job.__name__} failed: {e!r}")
        except Exception as e:  # noqa: BLE001
            log(f"loop error: {type(e).__name__}")
            if conn is not None:
                conn.close()
            conn = None
        if args.once:
            return 0
        time.sleep(poll)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Startup errors from signed exchange requests must not expose credentials.
        print(f'Executor startup failed ({type(exc).__name__})',file=sys.stderr)
        sys.exit(1)
