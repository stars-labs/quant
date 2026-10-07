"""Chronology, execution costs, cash flows and drawdown of the research replay."""
import sys
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
from trend_replay import Rule,replay


def frame(prices,opens=None):
    idx=pd.date_range('2026-01-30T00:00:00Z',periods=len(prices),freq='h')
    opens=prices if opens is None else opens
    return pd.DataFrame({'open':opens,'close':prices,
                         'high':[max(a,b) for a,b in zip(opens,prices)],
                         'low':[min(a,b) for a,b in zip(opens,prices)]},index=idx)


def test_signal_fills_at_next_open_and_deducts_both_fees():
    d=frame([10,10,10,12,12,8,8],[10,10,10,12,15,8,7])
    r=replay({'BTC':d},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1),fee=.002,slippage=.001)
    buy,sell=r['fills']
    assert buy['time']==d.index[4].isoformat() and buy['price']==15*1.001
    assert sell['time']==d.index[6].isoformat() and sell['price']==7*.999
    cost=20/1.003
    expected=cost/(15*1.001)*.998*(7*.999)*.998
    assert abs(sell['cash']-expected)<1e-10
    assert abs(r['equity_usdt']-(100-cost+expected))<1e-10
    assert r['paid_fees_usdt']>0


def test_future_prices_do_not_change_previous_fills():
    d=frame([10,10,10,12,12,13,14])
    first=replay({'BTC':d},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1))
    other=d.copy();other.loc[d.index[-1],['open','high','low','close']]=200
    second=replay({'BTC':other},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1))
    assert first['fills']==second['fills']


def test_drawdown_includes_unrealised_loss():
    d=frame([10,10,10,12,12,6])
    r=replay({'BTC':d},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1),fee=0,slippage=0)
    assert r['sells']==0 and r['hourly_close_max_drawdown']<-.09


def test_cash_constrained_and_no_duplicate_target_entry():
    d=frame([10,10,10,12,12,12,12,12])
    r=replay({a:d for a in ['BTC','ETH','SOL']},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1),monthly=25,order_cap=20)
    assert r['buys']==2 and r['cash_usdt']>=0
    assert [f['asset'] for f in r['fills']]==['BTC','ETH']


def test_monthly_contributions_are_not_returns():
    d=frame([10]*76)
    r=replay({'BTC':d},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1))
    assert r['funded_usdt']==200 and r['equity_usdt']==200
    assert r['time_weighted_return']==0 and r['hourly_close_max_drawdown']==0


def test_missing_duplicate_invalid_and_warmup_bars_rejected():
    d=frame([10]*10)
    start,end=d.index[3],d.index[-1]+pd.Timedelta(hours=1)
    bad=d.copy();bad.iloc[-1,bad.columns.get_loc('close')]=float('nan')
    for data in (d.drop(d.index[5]),pd.concat([d,d.iloc[-1:]]),bad,d.iloc[2:]):
        with pytest.raises(ValueError): replay({'BTC':data},Rule('tiny',2,1),start,end)


def test_exits_have_priority_over_new_entries():
    a=frame([10,10,10,12,12,8,8]);b=frame([10,10,10,10,10,12,12])
    r=replay({'BTC':a,'ETH':b},Rule('tiny',2,1),a.index[3],a.index[-1]+pd.Timedelta(hours=1),monthly=20)
    assert [f['side'] for f in r['fills']]==['buy','sell','buy']
    assert r['fills'][-1]['asset']=='ETH'


def test_new_deposit_does_not_erase_existing_drawdown():
    prices=[10]*4+[12]*43+[6]*30
    d=frame(prices)
    r=replay({'BTC':d},Rule('tiny',2,1),d.index[3],d.index[-1]+pd.Timedelta(hours=1),fee=0,slippage=0)
    assert r['funded_usdt']==200
    expected=-((20/1.003)*.5)/100
    assert abs(r['time_weighted_return']-expected)<1e-10
    assert abs(r['hourly_close_max_drawdown']-expected)<1e-10


def test_baseline_signal_times_match_public_state_machine():
    import strategy_record as sr
    d=frame([10]*168+[12,12,8,8,8])
    bars=[(int(t.timestamp()*1000)+3599999,float(r.high),float(r.low),float(r.close))
          for t,r in d.iterrows()]
    events=sr.step(bars,None,after_ms=0)
    r=replay({'BTC':d},Rule('baseline'),d.index[169],d.index[-1]+pd.Timedelta(hours=1))
    assert len(events)==len(r['fills'])==2
    for event,fill in zip(events,r['fills']):
        assert pd.Timestamp(fill['time']).value//1000000==event['ts']+1
