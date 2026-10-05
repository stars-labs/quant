"""Real PostgreSQL tests for upload-only tokens and owner-private displays."""

import copy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.getenv('RUNNER_TEST_DSN'), 'Set RUNNER_TEST_DSN for disposable DB tests')
class DisplayDatabaseTest(unittest.TestCase):
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
                CREATE SCHEMA quant; CREATE SCHEMA api; CREATE SCHEMA auth;
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF;
                END $$;
                GRANT USAGE ON SCHEMA api,quant,auth TO anon,authenticated;
                CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
                    SELECT nullif(current_setting('request.test_uid',true),'')::uuid
                $$;
                CREATE TABLE quant.users(id uuid PRIMARY KEY);
                INSERT INTO quant.users VALUES
                    ('00000000-0000-0000-0000-000000000001'),
                    ('00000000-0000-0000-0000-000000000002');
            """)
            migration = Path(__file__).resolve().parents[2] / 'migrations/043_runner_display_connections.sql'
            cur.execute(migration.read_text())

    @classmethod
    def tearDownClass(cls):
        with cls.conn.cursor() as cur:
            cur.execute('RESET ROLE; DROP SCHEMA api CASCADE; DROP SCHEMA quant CASCADE; DROP SCHEMA auth CASCADE')
        cls.conn.close()

    def sql(self, sql, args=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall() if cur.description else []

    def owner(self, number):
        self.sql('RESET ROLE')
        self.sql("SELECT set_config('request.test_uid',%s,false)", (f'00000000-0000-0000-0000-{number:012d}',))
        self.sql('SET ROLE authenticated')

    def anonymous(self):
        self.sql('RESET ROLE')
        self.sql("SELECT set_config('request.test_uid','',false)")
        self.sql('SET ROLE anon')

    def setUp(self):
        self.sql('RESET ROLE; TRUNCATE quant.runner_connections')
        self.owner(1)
        self.first = self.sql("SELECT api.create_runner_connection('My HTX','htx','live')")[0][0]
        self.report = {'version': 1, 'sequence': 1, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'status': 'healthy', 'venue': 'htx', 'environment': 'live', 'cash_usdt': 100,
            'equity_usdt': 200, 'funded_usdt': 200, 'trend_available_usdt': 0,
            'dca_available_usdt': 100, 'fees_usdt': .2,
            'positions': [{'strategy': 'trend', 'asset': 'BTC', 'quantity': .001,
                'price_usdt': 100000, 'cost_usdt': 100, 'realized_pnl_usdt': 0}],
            'fills': [{'client_id': 'first', 'strategy': 'trend', 'asset': 'BTC', 'side': 'buy',
                'quantity': .001, 'quote_usdt': 100, 'fee_usdt': .2, 'fee_rate': .002,
                'finished_at': datetime.now(timezone.utc).isoformat()}]}

    def tearDown(self):
        self.sql('RESET ROLE')

    def upload(self, report=None, token=None):
        from psycopg2.extras import Json
        return self.sql('SELECT api.upload_runner_report(%s,%s)',
            (token or self.first['upload_token'], Json(self.report if report is None else report)))[0][0]

    def test_upload_token_cannot_read_display_or_create_connection(self):
        import psycopg2
        self.anonymous()
        self.assertEqual(self.upload(), 'accepted')
        for sql in ['SELECT * FROM api.runner_connections',
                    "SELECT api.create_runner_connection('Other','htx','live')",
                    "SELECT api.revoke_runner_connection('00000000-0000-0000-0000-000000000001')"]:
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                self.sql(sql)

    def test_owner_isolation_and_no_token_hash_disclosure(self):
        import psycopg2
        self.upload()
        self.owner(2)
        self.assertEqual(self.sql('SELECT * FROM api.runner_connections'), [])
        self.assertFalse(self.sql('SELECT api.revoke_runner_connection(%s)', (self.first['id'],))[0][0])
        self.owner(1)
        self.assertEqual(len(self.sql('SELECT * FROM api.runner_connections')), 1)
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            self.sql('SELECT token_hash FROM quant.runner_connections')

    def test_replay_and_conflicting_sequence_rejected(self):
        import psycopg2
        self.anonymous()
        self.assertEqual(self.upload(), 'accepted')
        self.assertEqual(self.upload(), 'already_received')
        self.report['cash_usdt'] = 99
        with self.assertRaises(psycopg2.errors.RaiseException):
            self.upload()
        self.report['sequence'] = 2
        self.assertEqual(self.upload(), 'accepted')
        self.report['sequence'] = 1
        with self.assertRaises(psycopg2.errors.RaiseException):
            self.upload()

    def test_revocation_disables_upload(self):
        import psycopg2
        self.sql('SELECT api.revoke_runner_connection(%s)', (self.first['id'],))
        self.anonymous()
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            self.upload()

    def test_credentials_and_arbitrary_fields_rejected_at_every_level(self):
        import psycopg2
        self.anonymous()
        for location in [None, 'positions', 'fills']:
            for field in ['api_key', 'secret', 'info', 'command']:
                report = copy.deepcopy(self.report)
                target = report if location is None else report[location][0]
                target[field] = 'must-not-be-stored'
                with self.assertRaises(psycopg2.errors.RaiseException):
                    self.upload(report)
        self.owner(1)
        self.assertIsNone(self.sql('SELECT report FROM api.runner_connections')[0][0])

    def test_invalid_numbers_identity_and_stale_time_rejected(self):
        import psycopg2
        self.anonymous()
        changes = [('cash_usdt', -1), ('cash_usdt', 'NaN'), ('cash_usdt', None),
            ('sequence', True), ('sequence', 1.5), ('status', None), ('version', None),
            ('venue', 'gate'), ('environment', 'dry_run'),
            ('observed_at', (datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat()),
            ('observed_at', (datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())]
        for field, value in changes:
            report = copy.deepcopy(self.report)
            report[field] = value
            with self.assertRaises(psycopg2.Error):
                self.upload(report)

    def test_invalid_nested_fields_and_oversized_lists_rejected(self):
        import psycopg2
        self.anonymous()
        for key, field, value in [('fills','fee_rate',.004), ('fills','side',None),
            ('positions','quantity',None), ('positions','asset',None)]:
            report = copy.deepcopy(self.report)
            report[key][0][field] = value
            with self.assertRaises(psycopg2.Error):
                self.upload(report)
        report = copy.deepcopy(self.report)
        report['fills'] *= 51
        with self.assertRaises(psycopg2.Error):
            self.upload(report)

    def test_unknown_token_rejected(self):
        import psycopg2
        self.anonymous()
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            self.upload(token='0'*64)
