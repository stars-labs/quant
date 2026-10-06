from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.journal import Journal
from starslab_runner.attribution import attribution


class AttributionTest(unittest.TestCase):
    def test_partial_sale_base_and_quote_fees_reconcile_to_account_pnl(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Journal(Path(folder)/'account.sqlite')
            month=datetime.now(timezone.utc).strftime('%Y-%m-01')
            try:
                store.fund(month,100,100)
                store.reserve('t-buy','entry:1','signal:1','trend','BTC','buy',20)
                store.finish('t-buy',.1996,-20,.2,20)
                store.reserve('t-sell','exit:1','signal:1','trend','BTC','sell',.0998)
                store.finish('t-sell',-.0998,11.976,.0998,12)
                store.reserve('d-buy','dca:1','DCA-BTC','dca','BTC','buy',10)
                store.finish('d-buy',.0998,-10,.1,10)
                rows=attribution(store,{'BTC':110})
                trend=next(row for row in rows if row['strategy']=='trend')
                self.assertAlmostEqual(trend['realized_pnl_usdt'],1.976)
                self.assertAlmostEqual(trend['unrealized_pnl_usdt'],.978)
                self.assertAlmostEqual(trend['fees_usdt'],.064)
                equity=store.cash()+sum(row['quantity']*110 for row in store.holdings())
                self.assertAlmostEqual(sum(row['net_pnl_usdt'] for row in rows),equity-store.net_funding())
                store.cash_flow('withdraw',month,-10,0)
                equity=store.cash()+sum(row['quantity']*110 for row in store.holdings())
                self.assertAlmostEqual(sum(row['net_pnl_usdt'] for row in attribution(store,{'BTC':110})),equity-store.net_funding())
            finally:
                store.close()

    def test_closed_positions_do_not_require_current_price(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Journal(Path(folder)/'account.sqlite')
            try:
                store.fund(datetime.now(timezone.utc).strftime('%Y-%m-01'),100,100)
                store.reserve('buy','entry:1','signal:1','trend','BTC','buy',10)
                store.finish('buy',.1,-10,.1,10)
                store.reserve('sell','exit:1','signal:1','trend','BTC','sell',.1)
                store.finish('sell',-.1,12,.1,12)
                row=attribution(store,{})[0]
                self.assertEqual(row['realized_pnl_usdt'],2)
                self.assertEqual(row['unrealized_pnl_usdt'],0)
            finally:
                store.close()
