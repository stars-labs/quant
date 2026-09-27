-- 037: growth loop — attribution, per-coin subscriptions, the follow ledger, live-only stats.
--
-- 1. Attribution. Every URL the alert dispatcher sends carries ?ref=<channel> (tg_entry,
--    tg_exit, tg_weekly, tg_boost, tg_scan, tg_bind, tg_plan, …). The web writes it to
--    quant.web_events.campaign: on the landing page_view it is the URL's own ref; on later
--    conversion events (signup, telegram_bound) it is the browser's FIRST-touch ref. The
--    existing `ref` column stays what it was (document.referrer host, first event of a session).
-- 2. Per-coin subscription. telegram_links.coins = which house coins (strategy_record.ASSETS)
--    the user wants strategy_signals entries/exits for; NULL = all (the default), '{}' = none.
--    The Monday scorecard is not filtered. last_seen_at = the dispatcher saw this chat press a
--    button or send a command (the daily report's "weekly active subscribers").
-- 3. Follow ledger ("我跟了这笔"). quant.user_follows(user_id, trade_id): the user says they
--    followed a pushed signal — from the Telegram entry card's inline button (the dispatcher
--    maps chat → user via telegram_links) or from /record. Only LIVE (pushed) signals can be
--    followed: backfilled history was never sent to anyone. quant.follow_trades /
--    quant.follow_record are the single source of the personal record (net of fees, at the
--    signal's price — NOT the user's real fills). Owner-only through the API.
-- 4. Live-only stats. quant.strategy_live_record: signals actually pushed since launch
--    (live = true), next to the full backfilled record on /record.
--
-- Re-runnable: IF NOT EXISTS / CREATE OR REPLACE / DROP … IF EXISTS throughout.
--
-- Apply as the api-schema owner (postgres) on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/037_follow_ledger.sql
-- (NOTIFY pgrst, 'reload schema' is sent on COMMIT below.)

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Attribution
-- ---------------------------------------------------------------------------
ALTER TABLE quant.web_events ADD COLUMN IF NOT EXISTS campaign text;
ALTER TABLE quant.web_events DROP CONSTRAINT IF EXISTS web_events_campaign_chk;
ALTER TABLE quant.web_events
  ADD CONSTRAINT web_events_campaign_chk CHECK (campaign ~ '^[a-z0-9_]{1,32}$');
CREATE INDEX IF NOT EXISTS web_events_campaign_idx
  ON quant.web_events (campaign, ts DESC) WHERE campaign IS NOT NULL;
COMMENT ON COLUMN quant.web_events.campaign IS
  '?ref= channel (e.g. tg_entry). page_view: the landing URL''s own ref; other events: the '
  'browser''s first-touch ref.';

CREATE OR REPLACE VIEW api.web_events_in AS
  SELECT event, path, visitor, user_id, lang, ref, campaign FROM quant.web_events;
ALTER VIEW api.web_events_in SET (security_invoker = true);
GRANT INSERT ON api.web_events_in TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. Per-coin subscription + last activity
-- ---------------------------------------------------------------------------
ALTER TABLE quant.telegram_links ADD COLUMN IF NOT EXISTS coins text[];
ALTER TABLE quant.telegram_links ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;
ALTER TABLE quant.telegram_links DROP CONSTRAINT IF EXISTS telegram_links_coins_chk;
ALTER TABLE quant.telegram_links
  ADD CONSTRAINT telegram_links_coins_chk CHECK (
    coins IS NULL OR (cardinality(coins) <= 64
      AND array_to_string(coins, ',', '?') ~ '^([A-Z0-9]{1,12}(,[A-Z0-9]{1,12})*)?$'));
COMMENT ON COLUMN quant.telegram_links.coins IS
  'House coins for strategy_signals entries/exits: NULL = all, {} = none. Scorecard unfiltered.';
COMMENT ON COLUMN quant.telegram_links.last_seen_at IS
  'Last button press / bot command from this chat (set by the alert dispatcher).';

-- Appending columns keeps CREATE OR REPLACE valid; the 017 grants carry over.
CREATE OR REPLACE VIEW api.telegram_links AS
  SELECT user_id, link_token, chat_id IS NOT NULL AS bound, topics, created_at, bound_at, coins
  FROM quant.telegram_links;
ALTER VIEW api.telegram_links SET (security_invoker = true);
GRANT SELECT ON api.telegram_links TO authenticated;

CREATE OR REPLACE VIEW api.telegram_links_rw AS
  SELECT user_id, link_token, topics, coins FROM quant.telegram_links;
ALTER VIEW api.telegram_links_rw SET (security_invoker = true);
GRANT SELECT, INSERT, UPDATE ON api.telegram_links_rw TO authenticated;

-- ---------------------------------------------------------------------------
-- 3. Follow ledger
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quant.user_follows (
  user_id     uuid        NOT NULL DEFAULT auth.uid(),
  trade_id    bigint      NOT NULL REFERENCES quant.strategy_signals (id) ON DELETE CASCADE,
  followed_at timestamptz NOT NULL DEFAULT now(),
  source      text        NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'telegram')),
  PRIMARY KEY (user_id, trade_id)
);
CREATE INDEX IF NOT EXISTS user_follows_trade_idx ON quant.user_follows (trade_id);

-- Backfilled rows (live = false) were never pushed, so nobody can have followed them. Checked
-- for every role (web users and the dispatcher alike); SECURITY DEFINER because web users
-- have no privilege on quant.strategy_signals.
CREATE OR REPLACE FUNCTION quant.user_follows_live_only() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = quant AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM quant.strategy_signals WHERE id = NEW.trade_id AND live) THEN
    RAISE EXCEPTION 'trade % is not a live (pushed) signal', NEW.trade_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END
$$;
DROP TRIGGER IF EXISTS user_follows_live_only ON quant.user_follows;
CREATE TRIGGER user_follows_live_only BEFORE INSERT OR UPDATE ON quant.user_follows
  FOR EACH ROW EXECUTE FUNCTION quant.user_follows_live_only();

ALTER TABLE quant.user_follows ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_follows_owner ON quant.user_follows;
CREATE POLICY user_follows_owner ON quant.user_follows
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
DROP POLICY IF EXISTS user_follows_quant ON quant.user_follows;
CREATE POLICY user_follows_quant ON quant.user_follows
  FOR ALL TO quant USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, DELETE ON quant.user_follows TO authenticated, quant;

-- Mark / unmark from the web (owner RLS; user_id defaults to auth.uid()).
CREATE OR REPLACE VIEW api.user_follows AS
  SELECT user_id, trade_id, followed_at, source FROM quant.user_follows;
ALTER VIEW api.user_follows SET (security_invoker = true);
GRANT SELECT, INSERT, DELETE ON api.user_follows TO authenticated;

-- Every follow with its trade. net_ret comes from quant.strategy_trades (0.1% fee per side);
-- open_ret marks a still-open trade at the last closed 1h bar, same math as strategy_record.
CREATE OR REPLACE VIEW quant.follow_trades AS
SELECT f.user_id, f.trade_id, f.followed_at, f.source,
       t.strategy, t.asset, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price,
       t.net_ret, t.hold_days,
       CASE WHEN t.exit_ts IS NULL AND a.last_close IS NOT NULL
            THEN (a.last_close / t.entry_price) * power(0.999, 2) - 1
       END AS open_ret
FROM quant.user_follows f
JOIN quant.strategy_trades t ON t.id = f.trade_id
LEFT JOIN quant.strategy_assets a ON a.strategy = t.strategy AND a.asset = t.asset;

-- One row per user: the personal record. closed_compound = every closed followed trade
-- compounded in sequence with the same money (the same convention as strategy_record's
-- per-asset sleeve); open trades are reported separately, not folded in.
CREATE OR REPLACE VIEW quant.follow_record AS
SELECT user_id,
       count(*)::int                                          AS n_followed,
       count(*) FILTER (WHERE exit_ts IS NOT NULL)::int       AS n_closed,
       count(*) FILTER (WHERE net_ret > 0)::int               AS n_wins,
       count(*) FILTER (WHERE exit_ts IS NULL)::int           AS n_open,
       coalesce(exp(sum(ln(1 + net_ret))) - 1, 0)             AS closed_compound,
       max(net_ret)                                           AS best_ret,
       min(entry_ts)                                          AS first_entry_ts
FROM quant.follow_trades
GROUP BY user_id;

GRANT SELECT ON quant.follow_trades, quant.follow_record TO quant;

-- The caller's own rows only. Definer views (owner postgres) filtered by auth.uid(): web users
-- need no privilege on the quant.* views, and anon (auth.uid() NULL) sees nothing.
CREATE OR REPLACE VIEW api.my_follows AS
  SELECT trade_id, followed_at, source, asset, entry_ts, entry_price, exit_ts, exit_price,
         net_ret, hold_days, open_ret
  FROM quant.follow_trades
  WHERE user_id = auth.uid()
  ORDER BY entry_ts DESC;
GRANT SELECT ON api.my_follows TO authenticated;

CREATE OR REPLACE VIEW api.my_follow_record AS
  SELECT n_followed, n_closed, n_wins, n_open, closed_compound, best_ret, first_entry_ts
  FROM quant.follow_record
  WHERE user_id = auth.uid();
GRANT SELECT ON api.my_follow_record TO authenticated;

-- ---------------------------------------------------------------------------
-- 4. Live-only stats: signals actually pushed since launch (live = true). Same compounding
--    convention as follow_record (every closed live trade in sequence, same money).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW quant.strategy_live_record AS
SELECT strategy,
       count(*)::int                                          AS n_signals,
       count(*) FILTER (WHERE exit_ts IS NOT NULL)::int       AS n_closed,
       count(*) FILTER (WHERE net_ret > 0)::int               AS n_wins,
       count(*) FILTER (WHERE exit_ts IS NULL)::int           AS n_open,
       coalesce(exp(sum(ln(1 + net_ret))) - 1, 0)             AS closed_compound,
       min(entry_ts)                                          AS first_entry_ts
FROM quant.strategy_trades
WHERE live
GROUP BY strategy;
GRANT SELECT ON quant.strategy_live_record TO quant;

CREATE OR REPLACE VIEW api.strategy_live_record AS
  SELECT strategy, n_signals, n_closed, n_wins, n_open, closed_compound, first_entry_ts
  FROM quant.strategy_live_record;
GRANT SELECT ON api.strategy_live_record TO anon, authenticated;

NOTIFY pgrst, 'reload schema';

COMMIT;
