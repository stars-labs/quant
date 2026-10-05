"""Fixed signals, true adverse prices and public-record calibration."""
import sys
import math
from datetime import datetime,timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from trend_fee_analysis import analyze
from analyze_trend_fees import read_analysis
import strategy_record as sr

NOW=datetime(2026,10,5,tzinfo=timezone.utc)


def records():
    return [{'asset':a,'last_close':110,'last_ts':NOW,'start_ts':NOW.replace(month=1)}
            for a in ['BTC','ETH']]


def signals():
    return [{'asset':'BTC','entry_price':100,'exit_price':120,'exit_ts':NOW},
            {'asset':'ETH','entry_price':100,'exit_price':None,'exit_ts':None}]


def test_fees_and_slippage_do_not_change_signal_population():
    r=analyze(signals(),records(),[(.001,0),(.002,0),(.002,.0005)])
    assert (r['assets'],r['entries'],r['closed_trades'],r['open_trades'])==(2,2,1,1)
    returns=[x['equal_weight_return'] for x in r['results']]
    assert returns[0]>returns[1]>returns[2]
    expected=(1.2*.998**2+1.1*.998**2)/2-1
    assert math.isclose(returns[1],expected)
    assert math.isclose(returns[2],(1+expected)*(.9995/1.0005)-1)
    assert 'budget' in r['model'] and '100 USDT/20 USDT-cap' in r['limitations'][0]


def test_no_trades_hold_cash_and_no_profit_factor_invented():
    r=analyze([],records(),[(.002,0)])['results'][0]
    assert r['equal_weight_return']==0 and r['closed_win_rate'] is None
    assert r['closed_profit_factor'] is None


def test_invalid_cost_price_and_asset_rejected():
    for fee,slip in [(-.1,0),(0,float('nan')),(0,1)]:
        try: analyze(signals(),records(),[(fee,slip)])
        except ValueError: pass
        else: raise AssertionError('Invalid costs accepted')
    for price in [0,-1,float('inf')]:
        ss=signals();ss[0]['entry_price']=price
        try: analyze(ss,records(),[(.002,0)])
        except ValueError: pass
        else: raise AssertionError('Invalid price accepted')


class DB:
    def __init__(self,bad=False): self.bad=bad
    def cursor(self,**kwargs): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,params):
        if 'strategy_signals' in sql:
            self.rows=[{'asset':'BTC','entry_price':100,'exit_price':120,'exit_ts':NOW}]
        else:
            self.rows=[{'asset':a,'last_close':110,'last_ts':NOW,'start_ts':NOW.replace(month=1),
                        'sleeve_ret':(1.2*.999**2-1 if a=='BTC' else 0)+int(self.bad)} for a in sr.ASSETS]
    def fetchall(self): return self.rows


def test_read_analysis_checks_reference_before_publishing_sensitivity():
    r=read_analysis(DB(),[(.002,0)])
    assert r['public_record_calibration'].startswith('passed')
    try: read_analysis(DB(True),[(.002,0)])
    except ValueError: pass
    else: raise AssertionError('Calibration mismatch accepted')
