"""Real PostgreSQL live-journal regressions; requires EMPTY disposable DB."""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from htx_order_store import OrderStore


def check_orders(conn):
    from test_ccxt_executor_db import check_ledger_mode_isolation
    check_ledger_mode_isolation(conn)
    root=Path(__file__).resolve().parents[1]
    sql=(root/'migrations/039_executor_orders.sql').read_text()
    sql=re.sub(r'GRANT[^;]+;','',sql)
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute((root/'migrations/041_executor_fill_costs.sql').read_text())
    store=OrderStore(conn)
    month=datetime.now(timezone.utc).date().replace(day=1)
    assert store.budget('trend',month)==store.budget('dca',month)==0
    with conn.cursor() as cur:
        cur.execute("INSERT INTO quant.executor_funding VALUES ('HTX','live',%s,100,100,now())",(month,))
    assert store.budget('trend',month)==store.budget('dca',month)==100
    assert store.reserve('buy1','trend','BTC','buy','entry:1','pos1',20,.0015,.002)
    assert not store.reserve('duplicate','trend','BTC','buy','entry:1','pos1',20,.0015,.002)
    assert store.pending()==[('buy1','BTC','buy',None)]
    # Base-denominated fee: purchased0.2 BTC but held0.1996; cash out20.
    store.finish('buy1',0.1996,-20,.2,20)
    store.finish('buy1',0.1996,-20,.2,20)  # Exactly once after a restart.
    assert store.budget('trend',month)==80
    assert store.budget('dca',month)==100
    assert store.holdings()[0].qty==0.1996
    with conn.cursor() as cur:
        cur.execute("SELECT filled_amount,filled_cost,quoted_taker_rate,quoted_basic_rate "
                    "FROM quant.executor_orders WHERE client_id='buy1'")
        assert tuple(map(float,cur.fetchone()))==(.2,20,.0015,.002)
    # Partial exit retains remaining holding and recycles NET proceeds.
    store.reserve('sell1','trend','BTC','sell','exit:1','pos1',0.1,.0015,.002)
    store.finish('sell1',-0.1,11.97,.1,12)
    assert abs(store.holdings()[0].qty-0.0996)<1e-10
    assert store.budget('trend',month)==91.97
    with conn.cursor() as cur:
        cur.execute("SELECT quantity,close_date FROM quant.nautilus_trades WHERE position_id='pos1'")
        qty,closed=cur.fetchone()
        assert abs(float(qty)-0.0996)<1e-10 and closed is None
    store.reserve('dca1','dca','BTC','buy','dca:1','dca',10,.0015,.002)
    store.finish('dca1',0.1,-10.02,.1,10)  # Quote-denominated fee included.
    assert abs(store.budget('dca',month)-89.98)<1e-10
    # DB projection failure rolls back journal application, allowing reconciliation.
    store.reserve('dca2','dca','BTC','buy','dca:2','dca',10,.0015,.002)
    try:
        store.finish('dca2',.1,-10,.1,11)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid gross cost accepted')
    original=store.holdings
    def fail():
        raise RuntimeError('simulated projection failure')
    store.holdings=fail
    try:
        try:
            store.finish('dca2',0.1,-10,.1,10)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Missing failure')
    finally:
        store.holdings=original
    assert any(r[0]=='dca2' for r in store.pending())
    with conn.cursor() as cur:
        cur.execute("SELECT filled_amount,filled_cost FROM quant.executor_orders WHERE client_id='dca2'")
        assert cur.fetchone()==(None,None)
    assert abs(store.budget('dca',month)-89.98)<1e-10
    store.finish('dca2',0.1,-10,.1,10)
    # A second session cannot run or change funding concurrently.
    other=psycopg2.connect(os.environ['CCXT_TEST_DSN'])
    other.autocommit=True
    try:
        try:
            OrderStore(other)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Second executor got the lock')
    finally:
        other.close()
    store.reserve('sell2','trend','BTC','sell','exit:2','pos1',0.0996,.0015,.002)
    store.finish('sell2',-0.0996,12,.0996,12)
    h=next(h for h in store.holdings() if h.key=='pos1')
    assert abs(h.qty)<1e-10 and h.proceeds==23.97
    with conn.cursor() as cur:
        cur.execute("SELECT quantity,close_date,realized_pnl FROM quant.nautilus_trades WHERE position_id='pos1'")
        qty,closed,pnl=cur.fetchone()
        assert float(qty)==0.1996 and closed is not None and abs(float(pnl)-3.97)<1e-8
    next_month=month.replace(year=month.year+(month.month==12),month=month.month%12+1)
    assert store.budget('dca',next_month)==0  # No imaginary deposit at rollover.
    assert abs(store.budget('trend',next_month)-103.97)<1e-8  # Reusable capital only.
    assert abs(store.expected_cash()-183.95)<1e-8
    from htx_backfill_costs import enrich_order
    from test_htx_fill_costs import exchange
    with conn.cursor() as cur:
        cur.execute("UPDATE quant.executor_orders SET filled_amount=NULL,filled_cost=NULL,exchange_id='42' "
                    "WHERE client_id='buy1'")
        cur.execute("SELECT client_id,asset,side,exchange_id,asset_delta,cash_delta "
                    "FROM quant.executor_orders WHERE client_id='buy1'")
        row=cur.fetchone()
    assert enrich_order(conn,exchange(),row)
    assert not enrich_order(conn,exchange(),row)
    assert abs(store.expected_cash()-183.95)<1e-8
    print('Gross fill PostgreSQL checks passed: fee quote, atomic rollback, historical verification/idempotence')
    from htx_notifications import notify_htx
    with conn.cursor() as cur:
        cur.execute((root/'migrations/040_executor_notifications.sql').read_text())
        cur.execute("INSERT INTO quant.executor_status VALUES ('HTX',now(),true,'ok')")
    state, messages = {}, []
    notify_htx(conn,state,lambda *args: False,123)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM quant.executor_orders WHERE notified_at IS NOT NULL")
        assert cur.fetchone()[0] == 0
    def deliver(chat,text):
        messages.append(text)
        return True
    notify_htx(conn,state,deliver,123)
    assert len(messages)==1 and 'HTX 实盘成交' in messages[0]
    notify_htx(conn,{},deliver,123)
    assert len(messages)==1  # Database acknowledgement survives dispatcher restart.
    print('Notification PostgreSQL checks passed: migration, failed delivery retry, restart deduplication')
    print('Live journal PostgreSQL checks passed: budgets, fees, partial exit, replay, rollback, lock, month rollover')


if __name__=='__main__':
    conn=psycopg2.connect(os.environ['CCXT_TEST_DSN'])
    conn.autocommit=True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regnamespace('quant')")
            assert cur.fetchone()[0] is None,'Use EMPTY disposable DB'
        try:
            check_orders(conn)
        finally:
            with conn.cursor() as cur:
                cur.execute('DROP SCHEMA IF EXISTS quant CASCADE')
    finally:
        conn.close()
