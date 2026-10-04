"""Ledger integration against an EMPTY disposable PostgreSQL database.

Run: CCXT_TEST_DSN='dbname=postgres host=/tmp/... port=...' .venv-bots/bin/python
     tests/test_ccxt_executor_db.py
"""

import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))
from ccxt_executor import Fill, Ledger, Venue, realized


def check_ledger_mode_isolation(conn):
    # Real schema from the migrations, without requiring the Timescale extension.
    root = Path(__file__).resolve().parents[1]
    ddl = (root / "migrations/009_nautilus_trades.sql").read_text()
    ddl = ddl[ddl.index("CREATE TABLE"):ddl.index("SELECT create_hypertable")]
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA quant")
        cur.execute(ddl)
        cur.execute("ALTER TABLE quant.nautilus_trades ADD COLUMN asset_class text")

    class Markets:
        def load_markets(self):
            pass

    venues = [Venue("gate", mode, Markets()) for mode in ("dry_run", "testnet")]
    ledger = Ledger(conn)
    for venue in venues:
        for kind in ("trend", "dca"):
            ledger.add(kind, venue, "BTC", Fill(2, 100), None)

    dry, testnet = venues
    for kind in ("trend", "dca"):
        assert ledger.open_rows(kind, dry)["BTC"][2] == 2
        assert ledger.open_rows(kind, testnet)["BTC"][2] == 2

    ledger.add("dca", testnet, "BTC", Fill(1, 130), ledger.open_rows("dca", testnet)["BTC"])
    assert ledger.open_rows("dca", testnet)["BTC"][1:3] == (110, 3)
    assert ledger.open_rows("dca", dry)["BTC"][1:3] == (100, 2)

    ledger.close("trend", testnet, "BTC", ledger.open_rows("trend", testnet)["BTC"],
                 Fill(2, 120), 0.002)
    assert ledger.open_rows("trend", testnet) == {}
    assert ledger.open_rows("trend", dry)["BTC"][1:3] == (100, 2)
    with conn.cursor() as cur:
        cur.execute("SELECT realized_pnl, profit_pct FROM quant.nautilus_trades "
                    "WHERE environment='testnet' AND trader_id='FOLLOW-GATE'")
        pnl, ret = cur.fetchone()
        expected = realized(100, 120, 2, 0.002)
        assert abs(float(pnl) - expected[0]) < 1e-9
        assert abs(float(ret) - expected[1]) < 1e-9
    # Re-entry and restart read exactly the current holding.
    ledger.add("trend", testnet, "BTC", Fill(1, 125), None)
    assert Ledger(conn).open_rows("trend", testnet)["BTC"][1:3] == (125, 1)
    assert Ledger(conn).open_rows("trend", dry)["BTC"][1:3] == (100, 2)


if __name__ == "__main__":
    conn = psycopg2.connect(os.environ["CCXT_TEST_DSN"])
    conn.autocommit = True  # Match the executor: each write has its own timestamp.
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regnamespace('quant')")
            assert cur.fetchone()[0] is None, "Use an EMPTY disposable database"
        try:
            check_ledger_mode_isolation(conn)
        finally:
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS quant CASCADE")
    finally:
        conn.close()
    print("PostgreSQL ledger integration passed: isolated reads, DCA updates, exits and re-entry")
