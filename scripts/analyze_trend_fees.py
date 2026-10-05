"""Read-only house-rule fee/slippage sensitivity, with public-record calibration.

TIMESCALE_URL=... python scripts/analyze_trend_fees.py --json --slippage-bps 0 5 10
No order, funding or public-statistics writes. Generated output must not be committed.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
import strategy_record as sr
from trend_fee_analysis import analyze


def read_analysis(conn, scenarios):
    from psycopg2.extras import RealDictCursor
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT asset,entry_price,exit_price,entry_ts,exit_ts FROM quant.strategy_signals '
                    'WHERE strategy=%s AND asset=ANY(%s) ORDER BY asset,entry_ts',
                    (sr.STRATEGY,list(sr.ASSETS)))
        signals=cur.fetchall()
        cur.execute('SELECT asset,last_close,last_ts,start_ts,sleeve_ret FROM quant.strategy_record '
                    'WHERE strategy=%s AND asset=ANY(%s) ORDER BY asset',
                    (sr.STRATEGY,list(sr.ASSETS)))
        records=cur.fetchall()
    if {r['asset'] for r in records}!=set(sr.ASSETS):
        raise ValueError('Incomplete house universe')
    reference=analyze(signals,records,[(sr.FEE,0)])['results'][0]['per_asset']
    if any(not math.isclose(reference[r['asset']],float(r['sleeve_ret']),abs_tol=1e-9)
           for r in records):
        raise ValueError('Reference does not reproduce public record')
    result=analyze(signals,records,scenarios)
    result['public_record_calibration']='passed at published fee and zero slippage'
    return result


def main():
    import psycopg2
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--slippage-bps',type=float,nargs='+',default=[0])
    args=parser.parse_args()
    scenarios=[(fee,bps/10000) for bps in args.slippage_bps
               for fee in [0,.00085,.001,.0015,.002,.0025,.003]]
    try:
        conn=psycopg2.connect(os.environ['TIMESCALE_URL'])
        try:
            conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
            result=read_analysis(conn,scenarios)
        finally:
            conn.close()
    except Exception as exc:
        print(f'Fee analysis failed ({type(exc).__name__})',file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result,indent=2,default=str))
    else:
        print(result['model']+'; NOT live account returns')
        print(f"{result['period_start']} .. {result['asof']} | {result['closed_trades']} closed trades")
        print('Fee/side  Slippage/side  Rule return  Median asset  Profitable assets')
        for r in result['results']:
            print(f"{r['fee_per_side']:.3%}    {r['slippage_per_side']:.3%}        "
                  f"{r['equal_weight_return']:+.2%}       {r['median_asset_return']:+.2%}       "
                  f"{r['positive_assets']}/{result['assets']}")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
