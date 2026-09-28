"""Hourly warmup bars straight from IB (ibapi), for HonestTrendEquity.preload().

Why not the Nautilus adapter's request_bars: on a paper account (no real-time data
subscription) IB answers every historical request with warning 2188 ("Up-to-the-second
historical data requires additional subscription") but still sends the bars; the adapter
treats the warning as a failure, cancels the request (162) and returns nothing. A plain
ibapi request on its own client id gets the full history (verified 2026-09-28: NVDA
60 D × 1 hour RTH = 420 bars).

The last bar is dropped while it is still forming, so a restart mid-session doesn't feed
the same hour twice (once here, once live).
"""

from __future__ import annotations

import threading
import time

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

HOUR_S = 3600


def fetch_hourly(host: str, port: int, client_id: int, symbols: list[str], days: int,
                 rth: bool = True, timeout: float = 60.0) -> dict[str, list[tuple]]:
    """symbol → [(open_ts_s, open, high, low, close, volume), …] oldest first; a symbol that
    fails or times out maps to []. Never raises on IB errors (warmup is best effort)."""
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper

    class _App(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.rows: dict[int, list[tuple]] = {}
            self.done: set[int] = set()
            self.ready = threading.Event()

        def nextValidId(self, order_id):  # noqa: N802 — ibapi callback name
            self.ready.set()

        def historicalData(self, req_id, bar):  # noqa: N802
            self.rows.setdefault(req_id, []).append(
                (int(bar.date), float(bar.open), float(bar.high), float(bar.low),
                 float(bar.close), float(bar.volume)))

        def historicalDataEnd(self, req_id, start, end):  # noqa: N802
            self.done.add(req_id)

        def error(self, req_id, *args):
            # 2188 is the harmless paper-account warning; anything fatal ends that request.
            codes = [a for a in args if isinstance(a, int)]
            if req_id > 0 and codes and codes[-1] not in (2176, 2188):
                self.done.add(req_id)

    app = _App()
    out: dict[str, list[tuple]] = {s: [] for s in symbols}
    try:
        app.connect(host, port, client_id)
        threading.Thread(target=app.run, daemon=True).start()
        if not app.ready.wait(15):
            return out
        app.reqMarketDataType(3)  # delayed: what a paper account has
        for i, sym in enumerate(symbols, start=1):
            c = Contract()
            c.symbol, c.secType, c.exchange, c.currency = sym, "STK", "SMART", "USD"
            # formatDate=2 → bar.date is the bar's open time in epoch seconds
            app.reqHistoricalData(i, c, "", f"{days} D", "1 hour", "TRADES", int(rth), 2,
                                  False, [])
        deadline = time.monotonic() + timeout
        while len(app.done) < len(symbols) and time.monotonic() < deadline:
            time.sleep(0.2)
        now = time.time()
        for i, sym in enumerate(symbols, start=1):
            rows = sorted(app.rows.get(i, []))
            if rows and rows[-1][0] + HOUR_S > now:
                rows = rows[:-1]  # still forming
            out[sym] = rows
    except Exception:  # noqa: BLE001 — warmup must never stop the node from starting
        pass
    finally:
        try:
            app.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return out


def to_bars(rows: list[tuple], bar_type: BarType, price_precision: int = 2) -> list[Bar]:
    """Rows from fetch_hourly → Nautilus bars stamped at the bar's CLOSE (open + 1h), the way
    live EXTERNAL bars arrive."""
    bars = []
    for ts, o, h, lo, c, v in rows:
        t = (ts + HOUR_S) * 1_000_000_000
        bars.append(Bar(bar_type, Price(o, price_precision), Price(h, price_precision),
                        Price(lo, price_precision), Price(c, price_precision),
                        Quantity(max(v, 0.0), 0), t, t))
    return bars
