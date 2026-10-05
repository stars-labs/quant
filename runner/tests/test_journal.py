import sys
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from starslab_runner.journal import Journal


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'account.sqlite'
        self.store = Journal(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def reserve(self, cid='first', action='entry:1', side='buy', requested=20):
        self.store.fund(datetime.now(timezone.utc).strftime('%Y-%m-01'), 100, 100)
        return self.store.reserve(cid, action, 'position:1', 'trend', 'BTC', side, requested)

    def test_pending_survives_restart_and_blocks_new_orders(self):
        self.reserve()
        self.store.set_exchange_id('first', 'exchange-123')
        self.store.close()
        self.store = Journal(self.path)
        self.assertEqual(self.store.pending()[0]['exchange_id'], 'exchange-123')
        self.assertFalse(self.reserve())
        with self.assertRaises(RuntimeError):
            self.reserve('second', 'entry:2')

    def test_actual_base_fee_and_proceeds_reuse(self):
        month = datetime.now(timezone.utc).strftime('%Y-%m-01')
        self.store.fund(month, 100, 100)
        self.reserve()
        self.store.finish('first', .998, -20, 1, 20)
        self.assertEqual(self.store.cash(), 180)
        self.assertEqual(self.store.budget('trend', month), 80)
        self.assertEqual(self.store.holdings()[0]['quantity'], .998)
        self.reserve('sale', 'exit:1', 'sell', .998)
        self.store.finish('sale', -.998, 24.9001, .998, 24.95)
        self.assertAlmostEqual(self.store.budget('trend', month), 104.9001)
        self.assertEqual(self.store.holdings()[0]['quantity'], 0)

    def test_terminal_fill_is_idempotent_but_conflict_rejected(self):
        self.reserve()
        self.store.finish('first', .998, -20, 1, 20)
        self.store.finish('first', .998, -20, 1, 20)
        with self.assertRaises(ValueError):
            self.store.finish('first', .998, -19, 1, 19)
        self.assertEqual(self.store.cash(), 180)

    def test_invalid_fill_rolls_back_to_pending(self):
        self.reserve()
        for values in [(1, -21, 1, 21), (1, -20.04, 1, 20), (.99, -20, 1, 20), (float('nan'), -20, 1, 20), (1, -19, 1, 20)]:
            with self.assertRaises(ValueError):
                self.store.finish('first', *values)
            self.assertEqual(len(self.store.pending()), 1)
            self.assertEqual(self.store.cash(), 200)

    def test_no_fill_cancellation_unblocks_next_order(self):
        self.reserve()
        self.store.finish('first', 0, 0, 0, 0)
        self.assertTrue(self.reserve('second', 'entry:2'))

    def test_funding_is_confirmed_once(self):
        self.store.fund('2026-10-01', 100, 100)
        self.store.fund('2026-10-01', 100, 100)
        self.assertEqual(self.store.cash(), 200)
        with self.assertRaises(ValueError):
            self.store.fund('2026-10-01', 101, 100)
        for month, amount in [('2026-10-02', 100), ('2026-11-01', float('inf')), ('2026-11-01', -1)]:
            with self.assertRaises(ValueError):
                self.store.fund(month, amount, 100)

    def test_dca_funding_does_not_carry_into_next_month(self):
        self.store.fund('2026-09-01', 100, 100)
        self.store.fund('2026-10-01', 100, 100)
        self.assertEqual(self.store.budget('trend', '2026-10-01'), 200)
        self.assertEqual(self.store.budget('dca', '2026-10-01'), 100)

    def test_account_lock_and_private_database(self):
        with self.assertRaises(RuntimeError):
            Journal(self.path)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_exchange_id_cannot_change(self):
        self.reserve()
        self.store.set_exchange_id('first', '123')
        with self.assertRaises(ValueError):
            self.store.set_exchange_id('first', '456')

    def test_unfunded_purchase_and_unowned_sale_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.reserve('one', 'entry:1', 'p', 'trend', 'BTC', 'buy', 20)
        with self.assertRaises(ValueError):
            self.store.reserve('one', 'exit:1', 'p', 'trend', 'BTC', 'sell', 1)
        self.assertEqual(self.store.pending(), [])

    def test_funding_is_separate_for_each_strategy(self):
        self.store.fund(datetime.now(timezone.utc).strftime('%Y-%m-01'), 100, 100)
        with self.assertRaises(ValueError):
            self.store.reserve('one', 'entry:1', 'p', 'trend', 'BTC', 'buy', 101)

    def test_base_currency_sell_fee_cannot_make_holding_negative(self):
        self.reserve()
        self.store.finish('first', .998, -20, 1, 20)
        self.reserve('sale', 'exit:1', 'sell', .998)
        with self.assertRaises(ValueError):
            self.store.finish('sale', -.999, 24.95, .998, 24.95)
        self.assertEqual(len(self.store.pending()), 1)


if __name__ == '__main__':
    unittest.main()
