"""Retirement removes only the derived live projection and backend write access."""
import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.getenv('RUNNER_TEST_DSN'), 'Set RUNNER_TEST_DSN for disposable DB tests')
class RetireExecutionTest(unittest.TestCase):
    def test_private_audit_preserved_and_hosted_access_removed(self):
        import psycopg2
        conn = psycopg2.connect(os.environ['RUNNER_TEST_DSN'])
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                if cur.fetchone()[0] != 'starslab_runner_test':
                    raise RuntimeError('Only starslab_runner_test may be used')
                cur.execute('''
                    CREATE SCHEMA quant;
                    DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='quant')
                        THEN CREATE ROLE quant; END IF; END $$;
                    GRANT USAGE ON SCHEMA quant TO quant;
                    CREATE TABLE quant.executor_funding(amount numeric);
                    CREATE TABLE quant.executor_orders(client_id text);
                    CREATE TABLE quant.executor_status(healthy boolean);
                    INSERT INTO quant.executor_funding VALUES (200);
                    INSERT INTO quant.executor_orders VALUES ('preserved-original-id');
                    GRANT ALL ON quant.executor_funding,quant.executor_orders TO quant;
                    CREATE TABLE quant.nautilus_trades(venue text,environment text,trader_id text);
                    INSERT INTO quant.nautilus_trades VALUES
                        ('HTX','live','FOLLOW-HTX'),('HTX','live','DCA-HTX'),
                        ('HTX','dry_run','FOLLOW-HTX'),('GATE','dry_run','FOLLOW-GATE'),
                        ('BINANCE','testnet','FOLLOW-BINANCE');
                ''')
                migration = Path(__file__).parents[2] / 'migrations/046_retire_hosted_htx_execution.sql'
                cur.execute(migration.read_text())
                cur.execute('SELECT amount FROM quant.executor_funding')
                self.assertEqual(cur.fetchone()[0], 200)
                cur.execute('SELECT client_id FROM quant.executor_orders')
                self.assertEqual(cur.fetchone()[0], 'preserved-original-id')
                cur.execute('SELECT count(*) FROM quant.nautilus_trades')
                self.assertEqual(cur.fetchone()[0], 3)
                cur.execute("SELECT to_regclass('quant.executor_status')")
                self.assertIsNone(cur.fetchone()[0])
                cur.execute('SET ROLE quant')
                for table in ('executor_orders', 'executor_funding'):
                    with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                        cur.execute('SELECT * FROM quant.' + table)
        finally:
            with conn.cursor() as cur:
                cur.execute('RESET ROLE; DROP SCHEMA IF EXISTS quant CASCADE')
            conn.close()
