"""Fee sensitivity of fixed house signals; not the small-budget execution policy."""

from collections import defaultdict
import math
import statistics


def analyze(signals, records, scenarios):
    assets={r['asset']:r for r in records}
    if not assets or len(assets)!=len(records):
        raise ValueError('Missing or duplicated asset records')
    ratios=defaultdict(list)
    closed=[]
    for row in signals:
        asset=row['asset']
        if asset not in assets:
            raise ValueError('Signal asset absent from record')
        price=row['exit_price'] if row['exit_ts'] is not None else assets[asset]['last_close']
        entry=float(row['entry_price'])
        price=float(price)
        if any(not math.isfinite(v) or v<=0 for v in (entry,price)):
            raise ValueError('Invalid signal price')
        ratio=price/entry
        ratios[asset].append(ratio)
        if row['exit_ts'] is not None:
            closed.append(ratio)
    results=[]
    for fee,slippage in scenarios:
        if any(not math.isfinite(v) or not 0<=v<1 for v in (fee,slippage)):
            raise ValueError('Invalid execution cost')
        # Adverse execution: buy at P*(1+s), sell at P*(1-s); base buy/quote sell fees.
        factor=(1-fee)**2*(1-slippage)/(1+slippage)
        returns={a:math.prod(r*factor for r in ratios[a])-1 for a in assets}
        rr=[r*factor-1 for r in closed]
        wins=sum(r for r in rr if r>0)
        losses=-sum(r for r in rr if r<0)
        results.append({'fee_per_side':fee,'slippage_per_side':slippage,
            'equal_weight_return':statistics.mean(returns.values()),
            'median_asset_return':statistics.median(returns.values()),
            'positive_assets':sum(r>0 for r in returns.values()),
            'closed_win_rate':sum(r>0 for r in rr)/len(rr) if rr else None,
            'closed_mean_return':statistics.mean(rr) if rr else None,
            'closed_profit_factor':wins/losses if losses else None,
            'per_asset':returns})
    return {'model':'13 independent equal-weight sleeves; no cash-flow/budget constraints',
            'price_source':'Binance house signal prices; open positions valued as if liquidated',
            'limitations':['Not HTX fill history or the funded 100 USDT/20 USDT-cap executor',
                           'No intrabar equity curve: drawdown is not estimated',
                           'Asset selection unchanged; no reselection on evaluated data'],
            'assets':len(assets),'entries':len(signals),'closed_trades':len(closed),
            'open_trades':len(signals)-len(closed),
            'asof':min(r['last_ts'] for r in records),
            'period_start':min(r['start_ts'] for r in records),'results':results}
