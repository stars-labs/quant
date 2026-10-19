"""Daily account NetLiq snapshot → quant.account_snapshots (the verifiable equity curve).

Read-only by construction:
  - IB paper: connects to the Gateway with the dedicated read-only client id 9
    (the live node owns 8) and reads AccountSummary NetLiquidation. No orders.
  - Binance testnet: signed GET /api/v3/account on testnet.binance.vision, values
    holdings at current testnet prices. No orders.

One row per account per UTC day (unique index upserts on rerun). Run daily after the
US close via quant-account-snapshot.timer; safe to run any time.

Env (sops secrets.env + backtest-runner.env): TIMESCALE_URL; IB_HOST/IB_PORT optional
(defaults to the mesh Gateway); BINANCE_TESTNET_KEY/SECRET optional — the Binance leg
is skipped without them (the crypto node's keys live on oracle-arm-002, not here).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import psycopg2


def log(m: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {m}", flush=True)


def snapshot_ib() -> dict | None:
    """NetLiquidation of the IB paper account via a read-only API session."""
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper

    class S(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.summary: dict[str, tuple[str, str]] = {}
            self.acct = ""
            self.done = threading.Event()

        def error(self, reqId, code, msg, *a):
            if code not in (2104, 2105, 2106, 2107, 2119, 2158):
                log(f"ib msg {code}: {msg}")

        def managedAccounts(self, a):
            self.acct = a.split(",")[0]

        def accountSummary(self, reqId, account, tag, value, currency):
            self.summary[tag] = (value, currency)

        def accountSummaryEnd(self, reqId):
            self.done.set()

    host = os.environ.get("IB_HOST", "172.22.240.104")
    port = int(os.environ.get("IB_PORT", "4002"))
    app = S()
    app.connect(host, port, 9)
    threading.Thread(target=app.run, daemon=True).start()
    time.sleep(2)
    if not app.isConnected():
        log(f"IB gateway unreachable at {host}:{port}")
        return None
    app.reqAccountSummary(1, "All", "NetLiquidation,TotalCashValue,GrossPositionValue")
    app.done.wait(timeout=10)
    app.disconnect()
    if not app.acct.startswith("DU") or "NetLiquidation" not in app.summary:
        log(f"unexpected IB account state: {app.acct} {list(app.summary)}")
        return None
    nl, ccy = app.summary["NetLiquidation"]
    return {
        "account": f"IB-{app.acct}",
        "asset_class": "equity",
        "environment": "paper",
        "net_liq": float(nl),
        "currency": ccy,
        "detail": {k: v[0] for k, v in app.summary.items()},
    }


def main() -> int:
    dsn = os.environ.get("TIMESCALE_URL", "")
    if not dsn:
        print("TIMESCALE_URL required", file=sys.stderr)
        return 2
    snaps = []
    try:
        s = snapshot_ib()
        if s:
            snaps.append(s)
    except Exception as e:
        log(f"IB snapshot failed: {e!r}")
    if not snaps:
        log("nothing to record")
        return 1
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        for s in snaps:
            cur.execute(
                """INSERT INTO quant.account_snapshots
                     (account, asset_class, environment, net_liq, currency, detail)
                   VALUES (%(account)s,%(asset_class)s,%(environment)s,%(net_liq)s,%(currency)s,%(detail)s)
                   ON CONFLICT (account, snap_date) DO UPDATE
                     SET net_liq = EXCLUDED.net_liq, detail = EXCLUDED.detail, ts = now()""",
                {**s, "detail": json.dumps(s["detail"])},
            )
            log(f"recorded {s['account']}: {s['net_liq']:,.2f} {s['currency']}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
