-- Archive the imported source journal privately; no hosted live execution remains.
BEGIN;
REVOKE ALL ON quant.executor_funding,quant.executor_orders FROM quant;
DROP TABLE quant.executor_status;
-- These were a derived projection, not the source fills. Do not invent a sale.
-- The original orders/funding remain available to the DB owner for audit.
DELETE FROM quant.nautilus_trades
    WHERE venue='HTX' AND environment='live'
      AND trader_id IN ('FOLLOW-HTX','DCA-HTX');
COMMIT;
