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
