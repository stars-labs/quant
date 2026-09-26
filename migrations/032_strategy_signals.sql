-- 032: house strategy signals + public track record (the "wealth-effect" loop).
--
-- Users got no clear buy/sell points: the house trend rule (Donchian 1h 168/72, long-only —
-- the rule nautilus_crypto/donchian.py trades) called the Aug-18/19 rally on BTC/ETH/SOL but
-- nothing ever told a user. This adds a rule-based SIMULATED signal ledger (never advice,
-- never 代客理财) that the signal evaluator writes and the alert dispatcher / daily report /
-- web /record read:
--   quant.strategy_signals — one row per trade (entry + exit), live=false = backfilled history
--   quant.strategy_assets  — per-asset live state (last close, next bar's channel edges,
--                            buy&hold baseline)
--   quant.strategy_trades  — trades + net return (0.1% fee per side) + days held
--   quant.strategy_record  — per-asset stats; THE single source of truth for every consumer
--                            (they only average across assets, equal-weight, no rebalancing)
--   api.strategy_trades / api.strategy_record — public, anon-readable (like api.market_stress)
--
-- Also in this migration:
--   * Telegram topic 'dca_events' → 'strategy_signals' (nothing has written
--     quant.event_dca_triggers since 2026-06-07). Valid topics after this:
--     'strategy_signals', 'equity_trades'.
--   * Backtest-runner outage fix: policy backtest_jobs_select_own is TO public and calls
--     auth.uid(), so the runner (quant role) failed with "permission denied for schema auth".
--   * One-time quant.nautilus_trades data fix: node restarts left stale "open" incarnations
--     of the same (trader_id, position_id) — close them as exit_reason='superseded'.
--
-- Re-runnable: IF NOT EXISTS / CREATE OR REPLACE / idempotent UPDATEs throughout.
--
-- Apply as postgres on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/032_strategy_signals.sql
-- then (also sent below, on COMMIT):
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -c \"NOTIFY pgrst, 'reload schema'\""
-- Then seed history once (writes live=false, pre-notified rows — never pushed):
--   sops exec-env secrets.env '.venv-bots/bin/python strategies/signal_evaluator.py --backfill 2026-01-01'

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Trades. entry_level / exit_level = the channel edge the close broke (168-bar high /
--    72-bar low), stored so every message can show "close X broke Y" verbatim.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quant.strategy_signals (
  id                bigserial   PRIMARY KEY,
  strategy          text        NOT NULL,              -- 'donchian_1h'
  asset             text        NOT NULL,              -- 'BTC' | 'ETH' | 'SOL'
  entry_ts          timestamptz NOT NULL,              -- close time of the breakout bar
  entry_price       float8      NOT NULL,              -- that bar's close
  entry_level       float8      NOT NULL,              -- max HIGH of the prior 168 bars
  exit_ts           timestamptz,                       -- NULL while the position is open
  exit_price        float8,
  exit_level        float8,                            -- min LOW of the prior 72 bars
  live              boolean     NOT NULL DEFAULT true, -- false = backfilled history, never a live call
  entry_notified_at timestamptz,                       -- set by the dispatcher (or backfill)
  exit_notified_at  timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (strategy, asset, entry_ts)
);
-- At most one open position per (strategy, asset).
CREATE UNIQUE INDEX IF NOT EXISTS strategy_signals_one_open
  ON quant.strategy_signals (strategy, asset) WHERE exit_ts IS NULL;

GRANT SELECT, INSERT, UPDATE ON quant.strategy_signals TO quant;
GRANT USAGE ON SEQUENCE quant.strategy_signals_id_seq TO quant;

-- ---------------------------------------------------------------------------
-- 2. Per-asset live state. start_* is the buy&hold baseline (close of the first bar at/after
--    the record start) and is written ONLY by --backfill; the live sweep refreshes the rest.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quant.strategy_assets (
  strategy     text        NOT NULL,
  asset        text        NOT NULL,
  start_ts     timestamptz,
  start_price  float8,
  last_ts      timestamptz,                 -- close time of the last closed 1h bar
  last_close   float8,
  channel_high float8,                      -- max HIGH of the last 168 closed bars = next entry trigger
  channel_low  float8,                      -- min LOW of the last 72 closed bars   = next exit trigger
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (strategy, asset)
);

GRANT SELECT, INSERT, UPDATE ON quant.strategy_assets TO quant;

-- ---------------------------------------------------------------------------
-- 3. Trades + net return. Fee: 0.1% per side (Binance spot taker) →
--    net = (exit/entry) * 0.999^2 - 1. Open rows: net_ret NULL, hold_days counts to now().
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW quant.strategy_trades AS
SELECT id, strategy, asset,
       entry_ts, entry_price, entry_level,
       exit_ts, exit_price, exit_level,
       live, entry_notified_at, exit_notified_at, created_at,
       CASE WHEN exit_ts IS NOT NULL
            THEN (exit_price / entry_price) * power(0.999, 2) - 1
       END AS net_ret,
       round((extract(epoch FROM coalesce(exit_ts, now()) - entry_ts) / 86400)::numeric, 1)
         AS hold_days
FROM quant.strategy_signals;

-- ---------------------------------------------------------------------------
-- 4. Per-asset record — THE single source of truth for all stats (Telegram, daily report,
--    web). sleeve_ret = following every signal on this asset (closed trades compounded ×
--    the open position marked to market as if sold at last_close, both fees);
--    hold_ret = buy&hold from start_price. Consumers: portfolio_ret = avg(sleeve_ret),
--    hold_portfolio_ret = avg(hold_ret), win rate = sum(n_wins)/sum(n_closed).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW quant.strategy_record AS
WITH closed AS (
  SELECT strategy, asset,
         count(*)                                 AS n_closed,
         count(*) FILTER (WHERE net_ret > 0)      AS n_wins,
         exp(sum(ln(1 + net_ret))) - 1            AS closed_compound,
         max(net_ret)                             AS best_ret,
         avg(net_ret) FILTER (WHERE net_ret > 0)  AS avg_win,
         avg(net_ret) FILTER (WHERE net_ret <= 0) AS avg_loss
  FROM quant.strategy_trades
  WHERE exit_ts IS NOT NULL
  GROUP BY strategy, asset
), opened AS (
  SELECT a.strategy, a.asset,
         o.entry_ts, o.entry_price, o.live,
         (a.last_close / o.entry_price) * power(0.999, 2) - 1 AS open_ret
  FROM quant.strategy_assets a
  JOIN quant.strategy_signals o
    ON o.strategy = a.strategy AND o.asset = a.asset AND o.exit_ts IS NULL
)
SELECT a.strategy, a.asset,
       a.start_ts, a.start_price, a.last_ts, a.last_close, a.channel_high, a.channel_low,
       coalesce(c.n_closed, 0)::int         AS n_closed,
       coalesce(c.n_wins, 0)::int           AS n_wins,
       coalesce(c.closed_compound, 0)       AS closed_compound,
       c.best_ret, c.avg_win, c.avg_loss,
       o.entry_ts                           AS open_entry_ts,
       o.entry_price                        AS open_entry_price,
       o.live                               AS open_live,
       o.open_ret,
       (1 + coalesce(c.closed_compound, 0)) * (1 + coalesce(o.open_ret, 0)) - 1 AS sleeve_ret,
       a.last_close / a.start_price - 1     AS hold_ret
FROM quant.strategy_assets a
LEFT JOIN closed c ON c.strategy = a.strategy AND c.asset = a.asset
LEFT JOIN opened o ON o.strategy = a.strategy AND o.asset = a.asset
ORDER BY a.strategy, a.asset;

-- The dispatcher (arm-002) and the daily report (game box) log in as quant and read these
-- views. Views created by postgres carry no quant privilege (the schema's default ACL only
-- covers authenticated/service_role), so grant it explicitly.
GRANT SELECT ON quant.strategy_trades, quant.strategy_record TO quant;

-- ---------------------------------------------------------------------------
-- 5. Public API (PostgREST): the track record is public, same pattern as api.market_stress.
--    Plain (definer) views — anon needs no grant on the quant.* base tables. The
--    *_notified_at bookkeeping columns stay internal.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW api.strategy_trades AS
  SELECT id, strategy, asset,
         entry_ts, entry_price, entry_level,
         exit_ts, exit_price, exit_level,
         live, created_at, net_ret, hold_days
  FROM quant.strategy_trades
  ORDER BY entry_ts DESC;
GRANT SELECT ON api.strategy_trades TO anon, authenticated;

CREATE OR REPLACE VIEW api.strategy_record AS
  SELECT strategy, asset,
         start_ts, start_price, last_ts, last_close, channel_high, channel_low,
         n_closed, n_wins, closed_compound, best_ret, avg_win, avg_loss,
         open_entry_ts, open_entry_price, open_live, open_ret,
         sleeve_ret, hold_ret
  FROM quant.strategy_record;
GRANT SELECT ON api.strategy_record TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 6. Telegram topics: 'dca_events' is dead → 'strategy_signals' (no compat). Replace in
--    place, keeping order and dropping a duplicate if the row already had both.
-- ---------------------------------------------------------------------------
UPDATE quant.telegram_links t
   SET topics = (SELECT array_agg(topic ORDER BY first_pos)
                   FROM (SELECT topic, min(pos) AS first_pos
                           FROM unnest(array_replace(t.topics, 'dca_events', 'strategy_signals'))
                                WITH ORDINALITY AS u(topic, pos)
                          GROUP BY topic) d)
 WHERE 'dca_events' = ANY (t.topics);

ALTER TABLE quant.telegram_links ALTER COLUMN topics SET DEFAULT '{strategy_signals}';
COMMENT ON COLUMN quant.telegram_links.topics IS
  'Subscribed streams: strategy_signals (house strategy buy/sell + weekly scorecard), '
  'equity_trades (US-equity paper trades).';

-- ---------------------------------------------------------------------------
-- 7. Backtest runner (quant role): backtest_jobs_select_own is TO public, so its
--    auth.uid() is evaluated for quant too → needs USAGE on schema auth + EXECUTE. Table
--    privileges inside auth are NOT granted (auth.users stays unreadable), as in 031.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA auth TO quant;
GRANT EXECUTE ON FUNCTION auth.jwt(), auth.uid(), auth.role(), auth.email() TO quant;

-- ---------------------------------------------------------------------------
-- 8. One-time data fix: a node restart re-opens the same position_id with a new open_date
--    and the older row was never closed. Close every unclosed row that has a LATER row for
--    the same (trader_id, position_id) at that next row's open_date. close_rate /
--    realized_pnl / profit_pct stay NULL (no fill happened). TradeLedger.record_open does
--    the same going forward. Idempotent: a second run matches nothing.
-- ---------------------------------------------------------------------------
UPDATE quant.nautilus_trades t
   SET close_date  = n.next_open,
       exit_reason = 'superseded',
       synced_at   = now()
  FROM (SELECT trader_id, position_id, open_date,
               lead(open_date) OVER (PARTITION BY trader_id, position_id
                                     ORDER BY open_date) AS next_open
          FROM quant.nautilus_trades) n
 WHERE t.trader_id = n.trader_id
   AND t.position_id = n.position_id
   AND t.open_date = n.open_date
   AND t.close_date IS NULL
   AND n.next_open IS NOT NULL;

NOTIFY pgrst, 'reload schema';

COMMIT;
