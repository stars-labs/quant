-- 035: opportunity scan ("机会雷达") — near-trigger / dip / funding views + 'daily_scan' topic.
--
-- signal_evaluator.py now also writes strategy_assets.high_30d (max HIGH of the last 720 1h
-- bars) and, hourly, quant.funding_rates: Binance USDT-perp funding for the top-30 perps by
-- volume ∪ the house assets. ann_7d = the last 7 days of ACTUAL funding summed × 365/7, so
-- 1h/4h/8h settlement intervals all annualise correctly. High positive = crowded longs (the
-- spot-long / perp-short carry earns it); negative = crowded shorts.
--
-- quant.opportunity_scan is the single source for the scan (Telegram digest + /scan): per
-- house asset, distance to its entry trigger (flat) or exit line (held), drawdown from the
-- 30-day high, and its funding. Thresholds live in the consumers.
--
-- Apply as the api-schema owner (postgres) on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/035_opportunity_scan.sql

BEGIN;

ALTER TABLE quant.strategy_assets ADD COLUMN IF NOT EXISTS high_30d float8;

CREATE TABLE IF NOT EXISTS quant.funding_rates (
  asset             text PRIMARY KEY,           -- base asset, e.g. 'BTC' (symbol BTCUSDT)
  symbol            text NOT NULL,
  last_rate         float8 NOT NULL,            -- latest settled rate, per settlement
  ann_7d            float8 NOT NULL,            -- sum of the last 7 days × 365/7
  n_7d              int NOT NULL,               -- settlements in those 7 days (21 = 8h cycle)
  quote_volume_24h  float8,
  updated_at        timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON quant.funding_rates TO quant;

CREATE OR REPLACE VIEW quant.opportunity_scan AS
  SELECT a.asset, a.last_ts, a.last_close, a.channel_high, a.channel_low, a.high_30d,
         o.id IS NOT NULL AS held,
         o.entry_ts AS held_since,
         CASE WHEN o.id IS NULL AND a.channel_high IS NOT NULL
              THEN a.channel_high / a.last_close - 1 END AS to_entry,
         CASE WHEN o.id IS NOT NULL AND a.channel_low IS NOT NULL
              THEN a.channel_low / a.last_close - 1 END AS to_exit,
         CASE WHEN a.high_30d IS NOT NULL THEN a.last_close / a.high_30d - 1 END AS from_high_30d,
         f.ann_7d AS funding_ann_7d
    FROM quant.strategy_assets a
    LEFT JOIN quant.strategy_signals o
           ON o.strategy = a.strategy AND o.asset = a.asset AND o.exit_ts IS NULL
    LEFT JOIN quant.funding_rates f ON f.asset = a.asset
   WHERE a.strategy = 'donchian_1h';
GRANT SELECT ON quant.opportunity_scan TO quant;

CREATE OR REPLACE VIEW api.opportunity_scan AS SELECT * FROM quant.opportunity_scan;
GRANT SELECT ON api.opportunity_scan TO anon, authenticated;
CREATE OR REPLACE VIEW api.funding_rates AS
  SELECT asset, symbol, last_rate, ann_7d, n_7d, quote_volume_24h, updated_at
    FROM quant.funding_rates ORDER BY ann_7d DESC;
GRANT SELECT ON api.funding_rates TO anon, authenticated;

UPDATE quant.telegram_links
   SET topics = array_append(topics, 'daily_scan')
 WHERE NOT ('daily_scan' = ANY (topics));
ALTER TABLE quant.telegram_links
  ALTER COLUMN topics SET DEFAULT '{strategy_signals,dca_boost,daily_scan}';
COMMENT ON COLUMN quant.telegram_links.topics IS
  'Subscribed streams: strategy_signals (house trend entries/exits + Monday scorecard), '
  'dca_boost (smart-DCA boost days), daily_scan (morning opportunity digest), '
  'equity_trades (IB paper opens/closes).';

NOTIFY pgrst, 'reload schema';

COMMIT;
