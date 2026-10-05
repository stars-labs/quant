BEGIN;
ALTER TABLE quant.executor_orders
    ADD COLUMN filled_amount numeric CHECK (filled_amount >= 0),
    ADD COLUMN filled_cost numeric CHECK (filled_cost >= 0),
    ADD COLUMN quoted_taker_rate numeric CHECK (quoted_taker_rate BETWEEN 0 AND 0.003),
    ADD COLUMN quoted_basic_rate numeric CHECK (quoted_basic_rate BETWEEN 0 AND 0.003),
    ADD CONSTRAINT executor_gross_pair CHECK ((filled_amount IS NULL) = (filled_cost IS NULL)),
    ADD CONSTRAINT executor_quote_pair CHECK ((quoted_taker_rate IS NULL) = (quoted_basic_rate IS NULL)),
    ADD CONSTRAINT executor_gross_done CHECK (filled_amount IS NULL OR status='done');
COMMIT;
