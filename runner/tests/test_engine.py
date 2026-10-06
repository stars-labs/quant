"""Exercise order ambiguity, strategy isolation and real fill accounting end to end."""

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.config import DEFAULT, validate
from starslab_runner.engine import tick
from starslab_runner.exchange import HTX
from starslab_runner.journal import Journal
from starslab_runner.reporting import report


class Exchange:
    def __init__(self):
        self.orders = {}
        self.matches = {}
        self.total = {'USDT':200,'BTC':0}
        self.created = 0
        self.fail_after_submit = False
        self.before_submit = lambda: None

    def spot_private_get_v2_user_uid(self):
        return {'code':200,'data':123}

    def spot_private_get_v1_account_accounts(self):
        return {'status':'ok','data':[{'id':456,'type':'spot','state':'working'}]}

    def market(self, symbol):
        return {'spot':True,'active':True,'limits':{'cost':{'min':1},'amount':{'min':.00001}}}

    def fetch_ticker(self, symbol):
        return {'ask':100,'bid':100}

    def fetch_trading_fee(self, symbol):
        return {'symbol':symbol,'taker':.0015,'info':{'takerFeeRate':.002}}

    def fetch_balance(self, params):
        return {'free':self.total.copy(),'total':self.total.copy()}

    def cost_to_precision(self, symbol, value):
        return f'{value:.2f}'

    def amount_to_precision(self, symbol, value):
        # Real ccxt truncates rather than rounding above an allocation.
        import math
        return f'{math.floor(value*1e8)/1e8:.8f}'

    def create_market_buy_order_with_cost(self, symbol, cost, params):
        return self.create(symbol,'buy',cost/100,params)

    def create_market_sell_order(self, symbol, qty, params):
        return self.create(symbol,'sell',qty,params)

    def create(self, symbol, side, qty, params):
        self.before_submit()
        self.created += 1
        oid, cid = str(self.created), params['clientOrderId']
        self.orders[oid] = {'id':oid,'clientOrderId':cid,'symbol':symbol,'side':side,
            'status':'closed','filled':qty,'cost':qty*100}
        currency, fee = ('BTC',qty*.002) if side=='buy' else ('USDT',qty*100*.002)
        self.matches[oid] = [{'amount':qty,'cost':qty*100,'fee':{'currency':currency,'cost':fee}}]
        self.total['BTC'] += qty-fee if side=='buy' else -qty
        self.total['USDT'] += -qty*100 if side=='buy' else qty*100-fee
        if self.fail_after_submit:
            raise TimeoutError('signed URL containing credential must not be logged')
        return self.orders[oid]

    def fetch_order(self, oid, symbol, params):
        if params.get('clientOrderId'):
            return next(row for row in self.orders.values() if row['clientOrderId']==params['clientOrderId'])
        return self.orders[oid]

    def fetch_order_trades(self, oid, symbol):
        return self.matches[oid]


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'account.sqlite'
        self.store = Journal(self.path)
        self.now = datetime.now(timezone.utc)
        self.store.fund(self.now.strftime('%Y-%m-01'),100,100)
        self.ex = Exchange()
        self.venue = HTX(self.ex,'live','123','456')
        self.config = copy.deepcopy(DEFAULT)
        self.config.update(assets=['BTC'],mode='live',allow_live=True,account_uid='123',spot_account_id='456',dca=False)
        self.data = {'version':1,'server_time':self.now.isoformat(),
            'assets':[{'asset':'BTC','last_close':100,'last_ts':(self.now-timedelta(hours=1)).isoformat(),
                'updated_at':self.now.isoformat()}],'targets':[{'asset':'BTC','id':42}],'dca':None}

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def step(self):
        return tick(self.store,self.venue,self.config,self.data,self.now)

    def test_decisions_explain_alignment_and_absent_signals(self):
        decisions = []
        self.assertEqual(tick(self.store,self.venue,self.config,self.data,self.now,decisions),'healthy')
        self.assertIn('entry_submitted',[row['reason'] for row in decisions])
        decisions.clear()
        tick(self.store,self.venue,self.config,self.data,self.now,decisions)
        self.assertIn('target_already_processed',[row['reason'] for row in decisions])
        self.assertEqual(self.ex.created,1)
        self.data['targets'] = []
        decisions.clear()
        tick(self.store,self.venue,self.config,self.data,self.now,decisions)
        self.assertIn('no_entry_signal',[row['reason'] for row in decisions])
        self.assertIn('exit_submitted',[row['reason'] for row in decisions])

    def test_decisions_identify_missing_confirmed_funding(self):
        self.store.db.execute('DELETE FROM funding')
        decisions = []
        tick(self.store,self.venue,self.config,self.data,self.now,decisions)
        self.assertIn('confirmed_budget_unavailable',[row['reason'] for row in decisions])
        self.assertEqual(self.ex.created,0)

    def test_reservation_committed_before_network_and_actual_fee_used(self):
        def committed():
            import sqlite3
            with sqlite3.connect(self.path) as observer:
                self.assertEqual(observer.execute("SELECT count(*) FROM orders WHERE status='pending'").fetchone()[0],1)
        self.ex.before_submit = committed
        self.assertEqual(self.step(),'healthy')
        row = self.store.db.execute('SELECT * FROM orders').fetchone()
        self.assertEqual(row['quoted_taker_rate'],.0015)
        display = report(self.store,self.config,{'BTC':100},'healthy')
        self.assertAlmostEqual(display['fills'][0]['fee_rate'],.002)
        self.assertAlmostEqual(display['equity_usdt'],200-display['fees_usdt'])

    def test_timeout_after_acceptance_is_recovered_after_restart_without_resubmit(self):
        self.ex.fail_after_submit = True
        with self.assertRaises(TimeoutError):
            self.step()
        self.assertEqual(len(self.store.pending()),1)
        self.store.close()
        self.store = Journal(self.path)
        self.ex.fail_after_submit = False
        self.assertEqual(self.step(),'healthy')
        self.assertEqual(self.ex.created,1)
        self.assertEqual(self.store.pending(),[])

    def test_unknown_submission_blocks_all_new_orders(self):
        self.store.reserve('unknown','entry:41','signal:41','trend','BTC','buy',20)
        with self.assertRaises(StopIteration):
            self.step()
        self.assertEqual(self.ex.created,0)
        self.assertEqual(len(self.store.pending()),1)

    def test_stale_feed_does_not_liquidate_position(self):
        self.step()
        self.data['targets'] = []
        self.data['server_time'] = (self.now-timedelta(minutes=3)).isoformat()
        with self.assertRaises(ValueError):
            self.step()
        self.assertEqual(self.ex.created,1)
        self.assertGreater(self.store.holdings()[0]['quantity'],0)

    def test_dca_does_not_sell_with_trend_exit_and_both_signals_are_idempotent(self):
        self.config['dca'] = True
        self.data['dca'] = {'day':self.now.date().isoformat(),'units':8,'computed_at':self.now.isoformat()}
        self.step()
        self.step()
        self.assertEqual(self.ex.created,2)
        self.data['targets'] = []
        self.step()
        holdings = {row['kind']:row['quantity'] for row in self.store.holdings()}
        self.assertAlmostEqual(holdings['trend'],0)
        self.assertGreater(holdings['dca'],0)
        self.assertEqual(self.ex.created,3)

    def test_new_signal_closes_old_position_before_new_entry(self):
        self.step()
        self.data['targets'][0]['id'] = 43
        self.step()
        positions = {row['position']:row['quantity'] for row in self.store.holdings()}
        self.assertAlmostEqual(positions['signal:42'],0)
        self.assertGreater(positions['signal:43'],0)
        self.assertEqual(self.ex.created,3)

    def test_simulation_never_calls_order_endpoint(self):
        self.venue = HTX(self.ex,'dry_run')
        self.config.update(mode='dry_run',allow_live=False,account_uid=None,spot_account_id=None)
        self.step()
        self.assertEqual(self.ex.created,0)
        self.assertGreater(self.store.holdings()[0]['quantity'],0)

    def test_wrong_account_rejected_before_order_submission(self):
        with self.assertRaises(ValueError):
            HTX(self.ex,'live','wrong','456')
        self.assertEqual(self.ex.created,0)

    def test_local_live_authorization_required(self):
        self.config['allow_live'] = False
        with self.assertRaises(ValueError):
            validate(self.config)
        with self.assertRaises(ValueError):
            self.step()
        self.assertEqual(self.ex.created,0)

    def test_simulation_config_cannot_drive_a_live_adapter(self):
        self.config.update(mode='dry_run',allow_live=False)
        with self.assertRaises(ValueError):
            self.step()
        self.assertEqual(self.ex.created,0)

    def test_report_contains_only_display_fields(self):
        self.step()
        display = report(self.store,self.config,{'BTC':100},'healthy')
        for prohibited in ['api_key','secret','allow_live','order_usdt','account_uid','spot_account_id','info']:
            self.assertNotIn(prohibited,str(display))
