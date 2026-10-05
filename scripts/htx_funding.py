"""Confirm a funded UTC month after depositing 200 USDT. No orders or transfers.

Requires TIMESCALE_URL and HTX_API_KEY/_SECRET/_SUBACCOUNT_UID/_SPOT_ACCOUNT_ID
in the environment; run on arm-002 where the API key's IP is authorized.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
from htx_order_store import OrderStore


def main():
    import ccxt
    import psycopg2

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--month', default=datetime.now(timezone.utc).strftime('%Y-%m-01'))
    args = ap.parse_args()
    month = datetime.strptime(args.month,'%Y-%m-%d').date()
    if month.day!=1 or month != datetime.now(timezone.utc).date().replace(day=1):
        raise ValueError('Only the current UTC month may be funded')
    ex = ccxt.htx({'apiKey':os.environ['HTX_API_KEY'],'secret':os.environ['HTX_API_SECRET'],
                  'enableRateLimit':True,'options':{'defaultType':'spot'}})
    uid=ex.spot_private_get_v2_user_uid()
    if uid.get('code')!=200 or str(uid.get('data'))!=os.environ['HTX_SUBACCOUNT_UID']:
        raise ValueError('UID mismatch')
    conn=psycopg2.connect(os.environ['TIMESCALE_URL'])
    conn.autocommit=True
    try:
        store=OrderStore(conn)  # Stop executor first: this refuses concurrent funding.
        if store.pending():
            raise ValueError('Resolve pending orders before recording funding')
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM quant.executor_funding WHERE venue='HTX' "
                        "AND environment='live' AND month=%s",(month,))
            if cur.fetchone():
                print('This month is already funded; no change')
                return 0
        balance=ex.fetch_balance({'type':'spot','accountId':os.environ['HTX_SPOT_ACCOUNT_ID']})
        if float(balance['free'].get('USDT') or 0)+1e-8 < store.expected_cash()+200:
            raise ValueError('Deposit of 200 additional USDT not present in free spot cash')
        with conn.cursor() as cur:
            cur.execute("INSERT INTO quant.executor_funding "
                        "(venue,environment,month,trend_usdt,dca_usdt) "
                        "VALUES ('HTX','live',%s,100,100)",(month,))
        print(f'{month}: confirmed trend100 + DCA100 USDT')
    finally:
        conn.close()
    return 0


if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'Funding refused ({type(exc).__name__}); no automatic trading',file=sys.stderr)
        sys.exit(1)
