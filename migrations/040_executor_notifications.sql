-- Private operator delivery acknowledgement; unrelated to execution state.
BEGIN;
ALTER TABLE quant.executor_orders ADD COLUMN notified_at timestamptz;
CREATE INDEX executor_orders_unnotified ON quant.executor_orders(finished_at)
    WHERE status='done' AND notified_at IS NULL;
COMMIT;
