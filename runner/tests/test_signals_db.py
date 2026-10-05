"""Optional migration tests, restricted to a disposable PostgreSQL database."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from starslab_runner.signals import validate_snapshot


@unittest.skipUnless(os.getenv('RUNNER_TEST_DSN'), 'Set RUNNER_TEST_DSN for disposable DB tests')
class SignalDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        cls.conn = psycopg2.connect(os.environ['RUNNER_TEST_DSN'])
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute('SELECT current_database()')
            if cur.fetchone()[0] != 'starslab_runner_test':
                cls.conn.close()
                raise RuntimeError('Only starslab_runner_test may be used')
            cur.execute("""
                CREATE SCHEMA quant;
                CREATE SCHEMA api;
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF;
                END $$;
                GRANT USAGE ON SCHEMA api TO anon, authenticated;
                CREATE TABLE quant.strategy_assets (
                    strategy text, asset text, last_close float8,
                    last_ts timestamptz, updated_at timestamptz);
                CREATE TABLE quant.strategy_signals (
                    strategy text, asset text, id bigint, exit_ts timestamptz);
                CREATE TABLE quant.dca_boost_days (
                    day date, units float8, computed_at timestamptz);
                INSERT INTO quant.strategy_assets VALUES
                    ('donchian_1h','BTC',65000,now()-interval '1 hour',now());
                INSERT INTO quant.strategy_signals VALUES ('donchian_1h','BTC',42,NULL);
                INSERT INTO quant.dca_boost_days VALUES ((now() AT TIME ZONE 'UTC')::date,2,now());
            """)
            migration = Path(__file__).resolve().parents[2] / 'migrations/042_runner_signal_snapshot.sql'
            cur.execute(migration.read_text())

    @classmethod
    def tearDownClass(cls):
        with cls.conn.cursor() as cur:
            cur.execute('RESET ROLE; DROP SCHEMA api CASCADE; DROP SCHEMA quant CASCADE;')
        cls.conn.close()

    def tearDown(self):
        with self.conn.cursor() as cur:
            cur.execute('RESET ROLE')

    def test_anonymous_feed_matches_runner_contract(self):
        with self.conn.cursor() as cur:
            cur.execute('SET ROLE anon; SELECT api.runner_signals()')
            data = cur.fetchone()[0]
        parsed = validate_snapshot(data, ['BTC'], datetime.now(timezone.utc))
        self.assertEqual(parsed['targets'], {'BTC': 42})
        self.assertEqual(parsed['dca']['units'], 2)

    def test_anonymous_cannot_write_or_read_underlying_tables(self):
        import psycopg2
        with self.conn.cursor() as cur:
            cur.execute('SET ROLE anon')
            for query in ['SELECT * FROM quant.strategy_signals',
                          'DELETE FROM quant.strategy_signals']:
                with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute(query)
