-- 034: smart-DCA "boost day" ledger + the 'dca_boost' Telegram topic.
--
-- strategies/signal_evaluator.py writes one row per FNG day (UTC): that day's Fear & Greed,
-- the latest closed BTC daily bar, and the accumulator's rule (strategies/dca_boost.py,
-- mirrors nautilus_crypto/accumulator.py) → units = 1 base + fear/deep-fear + dip boosts.
-- ytd_* = the rule replayed from 2026-01-01 vs a plain fixed-amount DCA (the honest
-- "does it help" number shown in the push). The alert dispatcher pushes a boosted day to
-- 'dca_boost' subscribers at most once per 7 days unless the multiple goes up
-- (FNG hovers around 25, so boosts flicker on and off); processed rows get notified_at,
-- pushed says whether a message went out.
--
-- Apply as the api-schema owner (postgres) on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/034_dca_boost_days.sql

BEGIN;

CREATE TABLE IF NOT EXISTS quant.dca_boost_days (
  day              date PRIMARY KEY,           -- the FNG value's UTC date
  fng              int NOT NULL,
  bar_day          date NOT NULL,              -- latest closed BTC daily bar used
  btc_close        float8 NOT NULL,
  high_30d         float8,                     -- NULL until a full 30-bar window
  drawdown         float8,                     -- btc_close / high_30d - 1
  units            float8 NOT NULL,            -- 1 = plain day, >1 = boost day
  fear_add         float8 NOT NULL,
  dip_add          float8 NOT NULL,
  ytd_days         int,
  ytd_boosted_days int,
  ytd_plain_cost   float8,
  ytd_smart_cost   float8,
  computed_at      timestamptz NOT NULL DEFAULT now(),
  notified_at      timestamptz,
  pushed           boolean NOT NULL DEFAULT false
);

GRANT SELECT, INSERT, UPDATE ON quant.dca_boost_days TO quant;

CREATE OR REPLACE VIEW api.dca_boost_days AS
  SELECT day, fng, bar_day, btc_close, high_30d, drawdown, units, fear_add, dip_add,
         ytd_days, ytd_boosted_days, ytd_plain_cost, ytd_smart_cost
    FROM quant.dca_boost_days
   ORDER BY day DESC;
GRANT SELECT ON api.dca_boost_days TO anon, authenticated;

-- Everyone already bound gets the new topic (the dead 'dca_events' they first subscribed
-- to was this kind of alert); new links default to both house topics.
UPDATE quant.telegram_links
   SET topics = array_append(topics, 'dca_boost')
 WHERE NOT ('dca_boost' = ANY (topics));
ALTER TABLE quant.telegram_links ALTER COLUMN topics SET DEFAULT '{strategy_signals,dca_boost}';
COMMENT ON COLUMN quant.telegram_links.topics IS
  'Subscribed streams: strategy_signals (house trend entries/exits + Monday scorecard), '
  'dca_boost (smart-DCA boost days), equity_trades (IB paper opens/closes).';

NOTIFY pgrst, 'reload schema';

COMMIT;
