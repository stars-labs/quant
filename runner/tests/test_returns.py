import sqlite3
import unittest

from starslab_runner.returns import observed_period_return


class ReturnTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
            CREATE TABLE funding(month TEXT,trend REAL,dca REAL);
            CREATE TABLE metadata(key TEXT,value TEXT);
            CREATE TABLE cash_flows(cash_delta REAL,created_at TEXT);
            CREATE TABLE equity_snapshots(sequence INTEGER,observed_at TEXT,equity REAL,net_funding REAL);
        ''')
        self.db.execute("INSERT INTO funding VALUES ('2026-10-01',100,0)")
        self.db.execute("INSERT INTO metadata VALUES ('funded-at:2026-10-01','2026-10-01T00:00:00+00:00')")

    def tearDown(self):
        self.db.close()

    def snapshot(self, day, equity, funding):
        self.db.execute('INSERT INTO equity_snapshots VALUES (?,?,?,?)',
                        (day, f'2026-10-{day:02d}T00:00:00+00:00', equity, funding))

    def flow(self, day, amount):
        self.db.execute('INSERT INTO cash_flows VALUES (?,?)',
                        (amount, f'2026-10-{day:02d}T00:00:00+00:00'))

    def result(self):
        return observed_period_return(self)

    def test_deposit_and_withdrawal_are_neutral(self):
        self.snapshot(2, 100, 100)
        self.flow(3, 50)
        self.flow(4, -20)
        self.snapshot(6, 130, 130)
        self.assertEqual(self.result()['return_pct'], 0)

    def test_mid_period_flow_weighting(self):
        self.snapshot(2, 100, 100)
        self.flow(4, 100)
        self.snapshot(6, 215, 200)
        self.assertAlmostEqual(self.result()['return_pct'], 10)

    def test_unknown_timing_unavailable(self):
        self.db.execute('DELETE FROM metadata')
        self.db.execute("INSERT INTO funding VALUES ('2026-11-01',50,0)")
        self.snapshot(2, 100, 100)
        self.snapshot(6, 160, 150)
        self.assertIsNone(self.result()['return_pct'])
        self.assertEqual(self.result()['unavailable_reason'], 'unknown_flow_timing')

    def test_legacy_opening_funding_price_change(self):
        self.db.execute('DELETE FROM metadata')
        self.snapshot(2, 99, 100)
        self.snapshot(6, 108.9, 100)
        self.assertAlmostEqual(self.result()['return_pct'], 10)

    def test_legacy_opening_with_known_period_deposit(self):
        self.db.execute('DELETE FROM metadata')
        self.snapshot(2, 100, 100)
        self.flow(4, 100)
        self.snapshot(6, 215, 200)
        self.assertAlmostEqual(self.result()['return_pct'], 10)

    def test_legacy_opening_reconciles_known_preperiod_withdrawal(self):
        self.db.execute('DELETE FROM metadata')
        self.flow(1, -20)
        self.snapshot(2, 80, 80)
        self.snapshot(6, 88, 80)
        self.assertAlmostEqual(self.result()['return_pct'], 10)

    def test_legacy_later_snapshot_mismatch_unavailable(self):
        self.db.execute('DELETE FROM metadata')
        self.snapshot(2, 100, 100)
        self.snapshot(6, 160, 150)
        self.assertEqual(self.result()['unavailable_reason'], 'unreconciled_cash_flows')

    def test_zero_capital_unavailable(self):
        self.snapshot(2, 0, 100)
        self.snapshot(6, 0, 100)
        self.assertEqual(self.result()['unavailable_reason'], 'nonpositive_capital')

    def test_prior_fees_are_already_in_baseline(self):
        self.snapshot(2, 99, 100)
        self.snapshot(6, 99, 100)
        self.assertEqual(self.result()['return_pct'], 0)

    def test_budget_only_flow_ignored(self):
        self.snapshot(2, 100, 100)
        self.db.execute("INSERT INTO cash_flows VALUES (0,'unknown')")
        self.snapshot(6, 110, 100)
        self.assertAlmostEqual(self.result()['return_pct'], 10)

    def test_unreconciled_flow_unavailable(self):
        self.snapshot(2, 100, 100)
        self.snapshot(6, 210, 200)
        self.assertEqual(self.result()['unavailable_reason'], 'unreconciled_cash_flows')

    def test_insufficient_observations(self):
        self.snapshot(2, 100, 100)
        self.assertIsNone(self.result()['return_pct'])

    def test_duplicate_observation_timestamp_unavailable(self):
        self.snapshot(2, 100, 100)
        self.snapshot(2, 110, 100)
        self.assertEqual(self.result()['unavailable_reason'], 'invalid_observation_times')

    def test_nonfinite_valuation_unavailable(self):
        self.snapshot(2, 100, 100)
        self.snapshot(6, float('inf'), 100)
        self.assertEqual(self.result()['unavailable_reason'], 'invalid_valuation')

    def test_negative_funding_component_unavailable(self):
        self.db.execute('UPDATE funding SET trend=110,dca=-10')
        self.snapshot(2, 100, 100)
        self.snapshot(6, 110, 100)
        self.assertEqual(self.result()['unavailable_reason'], 'invalid_cash_flow')

    def test_zero_equity_interval_then_deposit_is_neutral(self):
        self.flow(2, -100)
        self.snapshot(2, 0, 0)
        self.flow(4, 100)
        self.snapshot(6, 100, 100)
        self.assertEqual(self.result()['return_pct'], 0)

    def test_same_time_flows_reconcile_together(self):
        self.snapshot(2, 100, 100)
        self.flow(4, -20)
        self.flow(4, 50)
        self.snapshot(4, 130, 130)
        self.snapshot(6, 130, 130)
        self.assertEqual(self.result()['return_pct'], 0)

    def test_endpoint_deposit_has_zero_weight(self):
        self.snapshot(2, 100, 100)
        self.flow(6, 100)
        self.snapshot(6, 210, 200)
        self.assertAlmostEqual(self.result()['return_pct'], 10)

    def test_nonpositive_withdrawal_weighted_capital(self):
        self.snapshot(2, 100, 100)
        self.flow(3, -200)
        self.flow(6, 200)
        self.snapshot(6, 100, 100)
        self.assertEqual(self.result()['unavailable_reason'], 'nonpositive_capital')


if __name__ == '__main__':
    unittest.main()
