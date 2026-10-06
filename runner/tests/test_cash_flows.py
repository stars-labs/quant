from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.journal import Journal


class CashFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Journal(Path(self.tmp.name)/'account.sqlite')
        self.month = datetime.now(timezone.utc).strftime('%Y-%m-01')
        self.store.fund(self.month,100,100)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_withdrawal_is_idempotent_and_not_trading_loss(self):
        for _ in range(2):
            self.store.cash_flow('withdrawal-1',self.month,-20,-10)
        self.assertEqual(self.store.cash(),170)
        self.assertEqual(self.store.net_funding(),170)
        self.assertEqual(self.store.budget('trend',self.month),80)
        self.assertEqual(self.store.budget('dca',self.month),90)
        self.assertEqual(self.store.holdings(),[])
        with self.assertRaises(ValueError):
            self.store.cash_flow('withdrawal-1',self.month,-21,-10)

    def test_transfer_conserves_cash_and_rejects_overallocation(self):
        self.store.cash_flow('transfer-1',self.month,20,-20)
        self.assertEqual(self.store.cash(),200)
        self.assertEqual(self.store.net_funding(),200)
        self.assertEqual(self.store.budget('trend',self.month),120)
        self.assertEqual(self.store.budget('dca',self.month),80)
        with self.assertRaises(ValueError):
            self.store.cash_flow('too-much',self.month,81,-81)
        with self.assertRaises(ValueError):
            self.store.cash_flow('unconfirmed-deposit',self.month,10,0)

    def test_pending_order_prevents_cash_adjustment(self):
        self.store.reserve('order','entry:1','signal:1','trend','BTC','buy',20)
        with self.assertRaises(ValueError):
            self.store.cash_flow('withdraw',self.month,-10,0)

    def test_incremental_deposit_obeys_gross_monthly_caps_after_withdrawal(self):
        self.store.db.execute('DELETE FROM funding')
        self.store.fund(self.month,40,50)
        for _ in range(2):
            self.store.deposit('topup',self.month,60,50,100,100)
        self.assertEqual(self.store.cash(),200)
        self.store.cash_flow('withdraw',self.month,-20,-10)
        with self.assertRaises(ValueError):
            self.store.deposit('cap-bypass',self.month,20,10,100,100)
        self.assertEqual(self.store.net_funding(),170)

    def test_carry_moves_old_allocation_once_without_adding_funding(self):
        source = '2020-01-01'
        self.store.fund(source,10,50)
        cash = self.store.cash()
        for _ in range(2):
            self.store.carry_dca('carry',source,30)
        self.assertEqual(self.store.budget('dca',source),20)
        self.assertEqual(self.store.budget('dca',self.month),130)
        self.assertEqual(self.store.cash(),cash)
        self.assertEqual(self.store.net_funding(),cash)
        with self.assertRaises(ValueError):
            self.store.carry_dca('too-much',source,21)
        with self.assertRaises(ValueError):
            self.store.carry_dca('carry',source,31)
        with self.assertRaises(ValueError):
            self.store.carry_dca('current',self.month,1)

    def test_realized_profit_withdrawal_preserves_pnl_and_positive_cash(self):
        from starslab_runner.attribution import attribution
        from starslab_runner.history import record_snapshot
        self.store.reserve('profit-buy','entry:profit','signal:profit','trend','BTC','buy',100)
        self.store.finish('profit-buy',1,-100,1,100)
        self.store.reserve('profit-sell','exit:profit','signal:profit','trend','BTC','sell',1)
        self.store.finish('profit-sell',-1,150,1,150)
        self.store.cash_flow('profit-withdrawal',self.month,-150,-90)
        self.assertEqual(self.store.cash(),10)
        self.assertEqual(self.store.net_funding(),-40)
        self.assertEqual(attribution(self.store,{})[0]['net_pnl_usdt'],50)
        now=datetime.now(timezone.utc).isoformat()
        record_snapshot(self.store,1,now,now,10,10,-40,0)
