"""Verify historical HTX matches before adding missing gross-fill metadata.

Never submits an order or changes net movements, budgets, positions or notifications.
Requires executor identity/env; safe to rerun with the live executor running.
"""

import math
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
from htx_live import fill_deltas
from htx_fill_costs import fee_details


def enrich_order(conn, exchange, row):
    cid,asset,side,oid,qty,cash = row
    symbol = f'{asset}/USDT'
    if not oid:
        raise ValueError('Historical order lacks exchange ID')
    order = exchange.fetch_order(oid,symbol)
    if (str(order.get('id'))!=str(oid) or order.get('symbol')!=symbol
            or order.get('side')!=side or order.get('status') not in
            ('closed','canceled','expired','rejected')):
        raise ValueError('Historical order identity/status differs')
    matches = exchange.fetch_order_trades(oid,symbol) if order.get('filled') else []
    actual_qty,actual_cash = fill_deltas(order,matches)
    if (not math.isclose(actual_qty,float(qty),rel_tol=1e-10,abs_tol=1e-12)
            or not math.isclose(actual_cash,float(cash),rel_tol=1e-10,abs_tol=1e-8)):
        raise ValueError('Historical match differs from net journal')
    amount = float(order.get('filled') or 0)
    cost = float(order.get('cost') or 0) if amount else 0
    fee_details(side,qty,cash,amount,cost)
    with conn.cursor() as cur:
        cur.execute("""UPDATE quant.executor_orders SET filled_amount=%s,filled_cost=%s
            WHERE client_id=%s AND venue='HTX' AND environment='live' AND status='done'
            AND exchange_id=%s AND asset_delta=%s AND cash_delta=%s AND filled_amount IS NULL""",
            (amount,cost,cid,str(oid),qty,cash))
        return cur.rowcount==1


def main():
    import ccxt
    import psycopg2
    try:
        ex=ccxt.htx({'apiKey':os.environ['HTX_API_KEY'],'secret':os.environ['HTX_API_SECRET'],
                     'enableRateLimit':True,'options':{'defaultType':'spot'}})
        uid=ex.spot_private_get_v2_user_uid()
        if str(uid.get('data'))!=os.environ['HTX_SUBACCOUNT_UID']:
            raise ValueError('Unexpected HTX identity')
        accounts=ex.fetch_accounts()
        if not any(str(a['id'])==os.environ['HTX_SPOT_ACCOUNT_ID'] and a.get('type')=='spot'
                   for a in accounts):
            raise ValueError('Unexpected HTX spot account')
        ex.load_markets()
        with psycopg2.connect(os.environ['TIMESCALE_URL']) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT client_id,asset,side,exchange_id,asset_delta,cash_delta "
                            "FROM quant.executor_orders WHERE venue='HTX' AND environment='live' "
                            "AND status='done' AND filled_amount IS NULL ORDER BY finished_at")
                rows=cur.fetchall()
            count=sum(enrich_order(conn,ex,r) for r in rows)
        print(f'Verified gross-fill details added: {count}; net journal unchanged')
        return 0
    except Exception as exc:
        print(f'HTX fee backfill failed ({type(exc).__name__}); no orders submitted',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
