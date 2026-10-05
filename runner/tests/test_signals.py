import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from starslab_runner.signals import validate_snapshot


class SignalsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
        self.data = {'version': 1, 'server_time': self.now.isoformat(),
            'assets': [{'asset': 'BTC', 'last_close': 65000,
                'last_ts': (self.now-timedelta(hours=1)).isoformat(),
                'updated_at': self.now.isoformat()}],
            'targets': [{'asset': 'BTC', 'id': 42}],
            'dca': {'day': '2026-10-06', 'units': 2, 'computed_at': self.now.isoformat()}}

    def check(self):
        return validate_snapshot(self.data, ['BTC'], self.now)

    def test_valid_snapshot(self):
        self.assertEqual(self.check()['targets'], {'BTC': 42})

    def test_missing_markets_cannot_be_interpreted_as_exit(self):
        self.data['assets'] = []
        self.data['targets'] = []
        with self.assertRaises(ValueError):
            self.check()

    def test_feed_cannot_change_local_execution_config(self):
        for field in ['api_key', 'budget', 'allow_live', 'order', 'command']:
            altered = copy.deepcopy(self.data)
            altered[field] = 'anything'
            with self.assertRaises(ValueError):
                validate_snapshot(altered, ['BTC'], self.now)

    def test_stale_and_future_market_rows_rejected(self):
        for offset in [-10801, 1]:
            self.data['assets'][0]['last_ts'] = (self.now+timedelta(seconds=offset)).isoformat()
            with self.assertRaises(ValueError):
                self.check()

    def test_cached_feed_rejected(self):
        self.data['server_time'] = (self.now-timedelta(seconds=121)).isoformat()
        with self.assertRaises(ValueError):
            self.check()

    def test_duplicate_or_non_integer_signal_id_rejected(self):
        for signal_id in [True, 1.5, 0, '42']:
            self.data['targets'][0]['id'] = signal_id
            with self.assertRaises(ValueError):
                self.check()

    def test_duplicate_market_rejected(self):
        self.data['assets'].append(copy.deepcopy(self.data['assets'][0]))
        with self.assertRaises(ValueError):
            self.check()

    def test_numeric_nan_infinite_and_boolean_rejected(self):
        for value in [float('nan'), float('inf'), True, -1, '65000']:
            self.data['assets'][0]['last_close'] = value
            with self.assertRaises(ValueError):
                self.check()

    def test_dca_old_day_skipped_but_bad_multiple_rejected(self):
        self.data['dca']['day'] = '2026-10-05'
        self.assertIsNone(self.check()['dca'])
        self.data['dca']['units'] = 100
        with self.assertRaises(ValueError):
            self.check()

    def test_ambiguous_timezone_rejected(self):
        self.data['server_time'] = '2026-10-06T12:00:00'
        with self.assertRaises(ValueError):
            self.check()
