"""Cutover preserves order identity and rolls back an invalid snapshot."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

from starslab_runner.journal import Journal

spec = importlib.util.spec_from_file_location('cutover', Path(__file__).parents[2] / 'scripts/import_htx_journal.py')
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)


class ImportTests(unittest.TestCase):
    def snapshot(self):
        return {'funding': [{'month': '2026-10-01', 'trend_usdt': 100, 'dca_usdt': 100}],
                'orders': [{'venue': 'HTX', 'environment': 'live', 'client_id': 'existing',
                            'action_key': 'entry:123', 'position_key': 'HTX-signal-123',
                            'kind': 'trend', 'asset': 'BTC', 'side': 'buy', 'requested': 20,
                            'status': 'done', 'exchange_id': '456', 'asset_delta': .0001996,
                            'cash_delta': -20, 'filled_amount': .0002, 'filled_cost': 20,
                            'quoted_taker_rate': .0015, 'quoted_basic_rate': .002,
                            'created_at': '2026-10-01T12:00:00+00:00',
                            'finished_at': '2026-10-01T12:00:01+00:00'}]}

    def test_preserves_accounting_and_refuses_second_import(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Journal(Path(directory) / 'journal.sqlite')
            try:
                result = cutover.import_snapshot(store, self.snapshot(), '1', '2')
                self.assertEqual(result['cash_usdt'], 180)
                self.assertEqual(store.holdings()[0]['position'], 'signal:123')
                self.assertTrue(store.exists('entry:123'))
                self.assertEqual(store.db.execute('SELECT exchange_id FROM orders').fetchone()[0], '456')
                with self.assertRaises(ValueError):
                    cutover.import_snapshot(store, self.snapshot(), '1', '2')
                self.assertEqual(store.cash(), 180)
            finally:
                store.close()

    def test_invalid_snapshot_rolls_back_funding_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Journal(Path(directory) / 'journal.sqlite')
            try:
                snapshot = copy.deepcopy(self.snapshot())
                snapshot['orders'][0]['cash_delta'] = -30
                with self.assertRaises(ValueError):
                    cutover.import_snapshot(store, snapshot, '1', '2')
                self.assertEqual(store.cash(), 0)
                self.assertIsNone(store.db.execute('SELECT 1 FROM metadata').fetchone())
            finally:
                store.close()

    def test_pending_identity_survives_without_terminal_movements(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Journal(Path(directory) / 'journal.sqlite')
            try:
                snapshot = self.snapshot()
                row = snapshot['orders'][0]
                row.update(status='pending', asset_delta=0, cash_delta=0,
                           filled_amount=None, filled_cost=None, finished_at=None)
                cutover.import_snapshot(store, snapshot, '1', '2')
                self.assertEqual(store.pending()[0]['client_id'], 'existing')
                self.assertEqual(store.pending()[0]['exchange_id'], '456')
            finally:
                store.close()

    def test_absent_historical_quote_is_preserved_without_invention(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Journal(Path(directory) / 'journal.sqlite')
            try:
                snapshot = self.snapshot()
                snapshot['orders'][0].update(quoted_taker_rate=None, quoted_basic_rate=None)
                cutover.import_snapshot(store, snapshot, '1', '2')
                self.assertEqual(tuple(store.db.execute('SELECT quoted_taker_rate,quoted_basic_rate FROM orders').fetchone()), (None, None))
            finally:
                store.close()
