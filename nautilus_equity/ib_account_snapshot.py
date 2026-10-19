"""Read-only snapshot of the IB paper account: positions, recent executions, balances.

Answers "does the IB paper account have any trades / open positions?" straight from IB
(not our DB). Places NO orders. Connects with a dedicated client id so it can't collide
with a running node. Asserts the account is paper (DU...) and bails otherwise.

  IB_HOST (default 172.22.240.104)  IB_PORT (default 4002)  IB_CLIENT_ID (default 9)
"""

from __future__ import annotations

import os
import threading
import time

from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class Snapshot(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.accounts: list[str] = []
        self.positions: list[tuple] = []
        self.execs: list[tuple] = []
        self.summary: dict[str, str] = {}
        self._done = threading.Event()
        self._pos_done = threading.Event()

    def error(self, reqId, code, msg, *a):  # noqa: D401
        # 2104/2106/2158 are benign "market data farm OK" notices.
        if code not in (2104, 2106, 2158, 2107, 2119):
            print(f"  [ib msg {code}] {msg}")

    def managedAccounts(self, accountsList: str):
        self.accounts = [a for a in accountsList.split(",") if a]

    def position(self, account, contract, position, avgCost):
        if position != 0:
            self.positions.append((account, contract.symbol, contract.secType, position, avgCost))

    def positionEnd(self):
        self._pos_done.set()

    def execDetails(self, reqId, contract, execution):
        self.execs.append((contract.symbol, execution.side, execution.shares, execution.price, execution.time))

    def execDetailsEnd(self, reqId):
        self._done.set()

    def accountSummary(self, reqId, account, tag, value, currency):
        self.summary[tag] = f"{value} {currency}"

    def accountSummaryEnd(self, reqId):
        pass


def main() -> int:
    host = os.environ.get("IB_HOST", "172.22.240.104")
    port = int(os.environ.get("IB_PORT", "4002"))
    cid = int(os.environ.get("IB_CLIENT_ID", "9"))

    app = Snapshot()
    app.connect(host, port, cid)
    t = threading.Thread(target=app.run, daemon=True)
    t.start()
    time.sleep(2.0)

    if not app.isConnected():
        print(f"NOT CONNECTED to IB Gateway at {host}:{port}")
        return 1
    print(f"connected to IB Gateway {host}:{port} (clientId={cid})")

    # wait for managed accounts
    for _ in range(20):
        if app.accounts:
            break
        time.sleep(0.2)
    acct = app.accounts[0] if app.accounts else "?"
    print(f"account(s): {app.accounts}")
    if not acct.startswith("DU"):
        print(f"REFUSING: account {acct} is not an IB paper account (DU...)")
        app.disconnect()
        return 2

    app.reqAccountSummary(1, "All", "NetLiquidation,TotalCashValue,GrossPositionValue,AvailableFunds")
    app.reqPositions()
    app._pos_done.wait(timeout=8)
    app.reqExecutions(2, __import__("ibapi.execution", fromlist=["ExecutionFilter"]).ExecutionFilter())
    app._done.wait(timeout=8)
    time.sleep(1.0)

    print("\n=== account summary ===")
    for k in ("NetLiquidation", "TotalCashValue", "GrossPositionValue", "AvailableFunds"):
        if k in app.summary:
            print(f"  {k:20} {app.summary[k]}")

    print(f"\n=== open positions ({len(app.positions)}) ===")
    if not app.positions:
        print("  (none — account is flat)")
    for a, sym, sec, pos, cost in app.positions:
        print(f"  {sym:8} {sec:5} qty={pos:>10}  avgCost={cost:.2f}")

    print(f"\n=== executions reported this session ({len(app.execs)}) ===")
    if not app.execs:
        print("  (none returned — reqExecutions only returns the last 24h for THIS client)")
    for sym, side, sh, px, ts in app.execs:
        print(f"  {ts}  {side:4} {sym:8} {sh} @ {px}")

    app.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
