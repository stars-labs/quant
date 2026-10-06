from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.journal import Journal
from starslab_runner.funding_history import funding_history


class FundingHistoryTest(unittest.TestCase):
    def test_original_funding_and_cash_movements_keep_actual_times(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Journal(Path(folder)/'account.sqlite')
            month=datetime.now(timezone.utc).strftime('%Y-%m-01')
            try:
                store.fund(month,100,100,datetime.now(timezone.utc).isoformat())
                store.cash_flow('withdraw',month,-10,0)
                store.cash_flow('allocate',month,20,-20)
                rows=funding_history(store)
                self.assertEqual(len(rows),3)
                self.assertEqual({row['kind'] for row in rows},{'deposit','withdrawal','allocation'})
                self.assertTrue(all(row['confirmed_at'] for row in rows))
                self.assertEqual(sum(row['cash_delta_usdt'] for row in rows),store.net_funding())
                store.db.execute("DELETE FROM metadata WHERE key LIKE 'funded-at:%'")
                deposit=next(row for row in funding_history(store) if row['kind']=='deposit')
                self.assertIsNone(deposit['confirmed_at'])
                self.assertEqual(deposit['month'],month)
            finally: store.close()

    def test_carry_has_no_cash_flow_and_legacy_confirmation_stays_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Journal(Path(folder)/'account.sqlite')
            try:
                store.fund('2020-01-01',0,100)
                store.carry_dca('carry-old','2020-01-01',20)
                rows=funding_history(store)
                carry=[row for row in rows if row['kind']=='carry']
                self.assertEqual(len(carry),2)
                self.assertEqual(sum(row['cash_delta_usdt'] for row in carry),0)
                self.assertEqual(sum(row['dca_delta_usdt'] for row in carry),0)
                self.assertIsNone(next(row for row in rows if row['kind']=='deposit')['confirmed_at'])
            finally: store.close()
