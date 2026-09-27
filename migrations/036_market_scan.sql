-- 036: opportunity radar for US equities + commodities ("机会雷达" beyond crypto).
--
-- signal_evaluator.py sweep_markets (every 15 min, cheap: cached daily closes) writes one row
-- per asset: where the latest daily close sits against its own 52-week closing high and
-- 200-day average, computed by strategies/market_scan.py.
--   commodity  the 12 /commodities futures — closes read from quant.market_snapshots
--              (market_collector's findata pull), no extra API call
--   equity     SPY/QQQ/IWM/SMH + 8 mega caps + quant.semi_universe — Yahoo daily closes via
--              findata.closes_yahoo (free, cached per UTC day)
-- These are OBSERVATIONS, not buy/sell triggers: in scripts/screen_daily_breakout.py the daily
-- breakout rule picked in-sample (2014/2017-2023) lost to buy-and-hold out of sample (2024-now)
-- on these assets (numbers in that script's docstring). VIX comes from quant.market_stress
-- (already collected hourly).
-- Thresholds live in the consumers (alert_dispatcher.py, web $lib/scan.ts).
--
-- Re-runnable. Apply as the api-schema owner (postgres) on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/036_market_scan.sql

BEGIN;

CREATE TABLE IF NOT EXISTS quant.market_scan (
  asset_class    text NOT NULL CHECK (asset_class IN ('equity', 'commodity')),
  asset          text NOT NULL,            -- ticker ('NVDA') or findata future ('GC')
  grp            text NOT NULL,            -- equity: index|mega|semis; commodity: metals|energy|ags
  name_zh        text,                     -- NULL = show the ticker only
  name_en        text,
  last_ts        timestamptz NOT NULL,     -- the latest CLOSED daily bar
  last_close     float8 NOT NULL,
  high_52w       float8 NOT NULL,          -- max close of the last 252 bars (incl. the last)
  low_52w        float8 NOT NULL,
  from_high_52w  float8 NOT NULL,          -- last_close / high_52w - 1 (<= 0)
  ma200          float8 NOT NULL,          -- 200-day simple average of closes
  vs_ma200       float8 NOT NULL,          -- last_close / ma200 - 1
  ret_1m         float8 NOT NULL,          -- vs the close 21 bars earlier
  updated_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (asset_class, asset)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON quant.market_scan TO quant;

CREATE OR REPLACE VIEW api.market_scan AS
  SELECT asset_class, asset, grp, name_zh, name_en, last_ts, last_close, high_52w, low_52w,
         from_high_52w, ma200, vs_ma200, ret_1m, updated_at
    FROM quant.market_scan
   ORDER BY asset_class, from_high_52w DESC;
GRANT SELECT ON api.market_scan TO anon, authenticated;

COMMENT ON TABLE quant.market_scan IS
  'Opportunity radar for US equities + commodities: daily-close position vs the 52-week high '
  'and 200-day average (observations, not triggers). Writer: signal_evaluator.sweep_markets.';

NOTIFY pgrst, 'reload schema';

COMMIT;
