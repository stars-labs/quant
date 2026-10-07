"""Compare three fixed research candidates under small-account execution costs.

Use a directory of ASSET.json arrays [open_ms,open,high,low,close]. Output is
research data and must not be committed. No exchange keys or live journal access.
"""
import argparse
import json
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
import strategy_record as sr
from trend_replay import Rule,replay


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('data_dir',type=Path)
    p.add_argument('--start',default='2026-01-01T00:00:00Z')
    p.add_argument('--end',required=True,help='Exclusive UTC hourly boundary')
    p.add_argument('--assets',nargs='+',default=list(sr.ASSETS))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if len(set(a.assets))!=len(a.assets): p.error('Duplicate assets')
    frames={}
    for asset in a.assets:
        rows=json.loads((a.data_dir/f'{asset}.json').read_text())
        d=pd.DataFrame(rows,columns=['time','open','high','low','close'])
        d.index=pd.to_datetime(d.pop('time'),unit='ms',utc=True)
        frames[asset]=d
    # Fixed before inspecting the replay; do not select new grids from its results.
    buffer=(1+.0005)/((1-.0005)*(1-.002)**2)-1
    rules=[Rule('baseline'),Rule('slower',336,144),Rule('cost_buffer',buffer=buffer)]
    scenarios=[(0,0),(.001,.0005),(.002,.0005),(.002,.001),(.003,.001)]
    results=[replay(frames,r,a.start,a.end,fee=f,slippage=s) for r in rules for f,s in scenarios]
    a.output.write_text(json.dumps({'candidate_selection':'fixed three; no live promotion',
                                   'results':results},indent=2)+'\n')
    print('Rule          Fee/side Slip/side   TWR     MaxDD     PnL USDT  Buys')
    for r in results:
        print(f"{r['rule']:13} {r['fee_per_side']:7.2%} {r['slippage_per_side']:8.2%} "
              f"{r['time_weighted_return']:+7.2%} {r['hourly_close_max_drawdown']:8.2%} "
              f"{r['pnl_usdt']:+10.2f} {r['buys']:5}")
    return 0

if __name__=='__main__': raise SystemExit(main())
