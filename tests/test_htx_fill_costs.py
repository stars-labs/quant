"""Real fee units, normalization, unknown historical quotes and protected enrichment."""
import sys
import math
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'strategies'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from htx_fill_costs import fee_details,quantity
from htx_notifications import format_fills
from htx_backfill_costs import enrich_order


def rejects(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Expected rejected fee')


def test_buy_base_fee_and_sell_quote_fee():
    base,quote,cost,rate=fee_details('buy',.1996,-20,.2,20)
    assert math.isclose(base,.0004) and quote==0
    assert math.isclose(cost,.04) and math.isclose(rate,.002)
    base,quote,cost,rate=fee_details('sell',-.1,19.96,.1,20)
    assert base==0 and math.isclose(quote,.04) and math.isclose(rate,.002)
    assert fee_details('buy',0,0,0,0)==(0,0,0,0)


def test_invalid_or_excessive_fee_rejected():
    for row in [('buy',.21,-20,.2,20),('sell',-.1,21,.1,20),
                ('buy',.19,-20,.2,20),('buy',.2,-20,0,0),
                ('buy',float('nan'),-20,.2,20)]:
        rejects(lambda: fee_details(*row))


def test_display_explicit_actual_fee_and_discount_discrepancy():
    now=datetime.now(timezone.utc)
    text=format_fills([('cid','trend','BTC','buy',.1996,-20,now,.2,20,.0015,.002)],80,100)
    assert '0.0004 BTC' in text and '实扣 0.200%' in text
    assert '折后 0.150% / 基础 0.200%' in text and '实扣高于折后报价' in text
    assert quantity(.000000463383966989)=='0.000000463384'
    assert 'e-' not in quantity(.000037294924933748)


def test_unknown_gross_fee_not_reported_as_zero():
    now=datetime.now(timezone.utc)
    text=format_fills([('cid','trend','BTC','buy',.1996,-20,now,None,None,None,None)],80,100)
    assert '手续费明细待核对' in text and '实扣' not in text


class DB:
    def __init__(self): self.calls=[]; self.rowcount=1
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,params): self.calls.append((sql,params))


def exchange():
    return SimpleNamespace(fetch_order=lambda *args: {
        'id':'42','symbol':'BTC/USDT','side':'buy','status':'closed','filled':.2,'cost':20},
        fetch_order_trades=lambda *args:[{'amount':.2,'cost':20,
                                           'fee':{'currency':'BTC','cost':.0004}}])


def test_backfill_requires_matches_net_journal_and_only_updates_metadata():
    db=DB()
    assert enrich_order(db,exchange(),('cid','BTC','buy','42',.1996,-20))
    sql,params=db.calls[0]
    assert 'SET filled_amount=%s,filled_cost=%s' in sql
    assert 'SET asset_delta' not in sql and 'filled_amount IS NULL' in sql
    assert params[:2]==(.2,20)
    db.rowcount=0
    assert not enrich_order(db,exchange(),('cid','BTC','buy','42',.1996,-20))
    db=DB()
    rejects(lambda: enrich_order(db,exchange(),('cid','BTC','buy','42',.2,-20)))
    assert not db.calls


def test_backfill_identity_mismatch_no_writes():
    ex=exchange(); ex.fetch_order=lambda *args: {'id':'wrong'}
    db=DB()
    rejects(lambda: enrich_order(db,ex,('cid','BTC','buy','42',.1996,-20)))
    assert not db.calls
