-- 033: health-check heartbeats — the two monitoring hosts watch each other.
--
-- strategies/health_check.py runs every 10 min on oracle-arm-002 (role 'server', nur
-- quant-collectors) and on the game box (role 'desk', systemd --user). Each run upserts
-- its row here; each role alerts when the OTHER role's heartbeat goes stale, so a host
-- that is down entirely (and therefore can't alert about itself) is still reported.
-- `failing` = the check ids failing on that host at its last run (for eyeballing).
--
-- Apply as the api-schema owner (postgres) on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/033_health_heartbeats.sql

BEGIN;

CREATE TABLE IF NOT EXISTS quant.health_heartbeats (
  role    text PRIMARY KEY,               -- 'server' | 'desk'
  host    text NOT NULL,
  ts      timestamptz NOT NULL DEFAULT now(),
  failing text[] NOT NULL DEFAULT '{}'
);

GRANT SELECT, INSERT, UPDATE ON quant.health_heartbeats TO quant;

COMMIT;
