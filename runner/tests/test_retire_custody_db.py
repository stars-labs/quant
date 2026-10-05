"""Credential retirement preserves ordinary user preferences and their RLS."""

import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.getenv('RUNNER_TEST_DSN'), 'Set RUNNER_TEST_DSN for disposable DB tests')
class RetireCustodyTest(unittest.TestCase):
    def test_retired_fields_removed_and_preferences_preserved(self):
        import psycopg2
        with psycopg2.connect(os.environ['RUNNER_TEST_DSN']) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                if cur.fetchone()[0] != 'starslab_runner_test':
                    raise RuntimeError('Only starslab_runner_test may be used')
                try:
                    cur.execute("""
                        CREATE SCHEMA quant; CREATE SCHEMA api; CREATE SCHEMA auth;
                        DO $$ BEGIN
                            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role; END IF;
                        END $$;
                        GRANT USAGE ON SCHEMA api,quant,auth TO authenticated;
                        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
                            SELECT '00000000-0000-0000-0000-000000000001'::uuid
                        $$;
                        CREATE TABLE quant.user_preferences (
                            user_id uuid PRIMARY KEY, dca_plan jsonb, email_digest boolean,
                            display_name text, updated_at timestamptz,
                            binance_api_key text, binance_api_secret text,
                            binance_connected_at timestamptz);
                        INSERT INTO quant.user_preferences VALUES
                            ('00000000-0000-0000-0000-000000000001','{"monthly_usdt":200}',true,'Owner',now(),'test-only-key','test-only-secret',now()),
                            ('00000000-0000-0000-0000-000000000002','{}',false,'Other',now(),NULL,NULL,NULL);
                        ALTER TABLE quant.user_preferences ENABLE ROW LEVEL SECURITY;
                        CREATE POLICY owner ON quant.user_preferences USING (user_id=auth.uid());
                        GRANT SELECT,INSERT,UPDATE ON quant.user_preferences TO authenticated;
                        CREATE VIEW api.user_preferences WITH (security_invoker=true) AS SELECT * FROM quant.user_preferences;
                    """)
                    migration = Path(__file__).resolve().parents[2] / 'migrations/044_remove_hosted_exchange_credentials.sql'
                    cur.execute(migration.read_text())
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='quant' AND table_name='user_preferences'")
                    columns = {row[0] for row in cur.fetchall()}
                    self.assertEqual(columns,{'user_id','dca_plan','email_digest','display_name','updated_at'})
                    cur.execute('SET ROLE authenticated; SELECT dca_plan,email_digest,display_name FROM api.user_preferences')
                    self.assertEqual(cur.fetchall(),[({'monthly_usdt':200},True,'Owner')])
                    with self.assertRaises(psycopg2.errors.UndefinedColumn):
                        cur.execute('SELECT binance_api_secret FROM api.user_preferences')
                finally:
                    cur.execute('RESET ROLE; DROP SCHEMA api CASCADE; DROP SCHEMA quant CASCADE; DROP SCHEMA auth CASCADE')
