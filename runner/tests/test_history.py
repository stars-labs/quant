from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from starslab_runner.history import history, record_snapshot
from starslab_runner.journal import Journal


class HistoryTest(unittest.TestCase):
    def test_cash_flows_do_not_change_investment_pnl_and_hourly_sampling_keeps_latest(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Journal(Path(folder)/'account.sqlite')
            try:
                record_snapshot(store,1,'2026-10-06T12:00:00+00:00','2026-10-06T11:59:00+00:00',198,100,200,.2)
                record_snapshot(store,2,'2026-10-06T12:01:00+00:00','2026-10-06T11:59:00+00:00',198,100,200,.2)
                record_snapshot(store,3,'2026-10-06T13:00:00+00:00','2026-10-06T12:59:00+00:00',168,70,170,.2)
                record_snapshot(store,4,'2026-10-06T14:00:00+00:00','2026-10-06T13:59:00+00:00',268,170,270,.2)
                points = history(store)['points']
                self.assertEqual(len(points),3)
                self.assertIn('12:01',points[0]['observed_at'])
                self.assertEqual([row['net_pnl_usdt'] for row in points],[-2,-2,-2])
            finally:
                store.close()

    def test_stale_and_nonfinite_valuations_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Journal(Path(folder)/'account.sqlite')
            try:
                with self.assertRaises(ValueError):
                    record_snapshot(store,1,'2026-10-06T12:00:00+00:00','2026-10-06T08:00:00+00:00',200,100,200,0)
                with self.assertRaises(ValueError):
                    record_snapshot(store,2,'2026-10-06T12:00:00+00:00','2026-10-06T11:59:00+00:00',float('nan'),100,200,0)
                self.assertEqual(history(store)['points'],[])
            finally:
                store.close()

    def test_pause_keeps_valuation_time_and_history_without_faking_prices(self):
        from starslab_runner.reporting import paused_report
        from starslab_runner.config import DEFAULT
        with tempfile.TemporaryDirectory() as folder:
            store = Journal(Path(folder)/'account.sqlite')
            try:
                previous = {'venue':'htx','environment':'dry_run','sequence':1,'observed_at':'2026-10-06T12:00:00+00:00',
                    'status':'healthy','equity_usdt':198,'history':[]}
                decisions = [{'strategy':'account','asset':None,'reason':'signal_feed_failed','error_class':'ConnectionResetError'}]
                result = paused_report(store,previous,DEFAULT,'paused',decisions)
                self.assertEqual(result['observed_at'],previous['observed_at'])
                self.assertEqual(result['equity_usdt'],198)
                self.assertEqual(result['status'],'paused')
                self.assertNotIn('error_class',result['decisions'][0])
                self.assertEqual(previous['status'],'healthy')
                self.assertEqual(history(store)['points'],[])
            finally:
                store.close()
