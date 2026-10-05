-- HTX live order intents and confirmed monthly funding. No public API needed.
BEGIN;
CREATE TABLE quant.executor_funding (
    venue text NOT NULL,
    environment text NOT NULL CHECK (environment = 'live'),
    month date NOT NULL CHECK (extract(day FROM month) = 1),
    trend_usdt numeric NOT NULL CHECK (trend_usdt > 0 AND trend_usdt <= 100),
    dca_usdt numeric NOT NULL CHECK (dca_usdt > 0 AND dca_usdt <= 100),
    confirmed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (venue, environment, month)
);
CREATE TABLE quant.executor_orders (
    client_id text PRIMARY KEY,
    venue text NOT NULL,
    environment text NOT NULL CHECK (environment = 'live'),
    kind text NOT NULL CHECK (kind IN ('trend','dca')),
    asset text NOT NULL,
    side text NOT NULL CHECK (side IN ('buy','sell')),
    action_key text NOT NULL,
    position_key text NOT NULL,
    requested numeric NOT NULL CHECK (requested > 0),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
    exchange_id text,
    asset_delta numeric NOT NULL DEFAULT 0,
    cash_delta numeric NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (venue, environment, action_key)
);
CREATE INDEX executor_orders_pending ON quant.executor_orders(venue,environment)
    WHERE status='pending';
CREATE TABLE quant.executor_status (
    venue text PRIMARY KEY,
    checked_at timestamptz NOT NULL DEFAULT now(),
    healthy boolean NOT NULL,
    detail text NOT NULL
);
GRANT SELECT, INSERT ON quant.executor_funding TO quant;
GRANT SELECT, INSERT, UPDATE ON quant.executor_orders TO quant;
GRANT SELECT, INSERT, UPDATE ON quant.executor_status TO quant;
COMMIT;
