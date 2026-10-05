-- One database snapshot of public research data. No execution or account access.
BEGIN;

CREATE FUNCTION api.runner_signals() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT jsonb_build_object(
        'version', 1,
        'server_time', statement_timestamp(),
        'assets', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'asset', asset, 'last_close', last_close, 'last_ts', last_ts,
            'updated_at', updated_at) ORDER BY asset)
            FROM quant.strategy_assets WHERE strategy='donchian_1h'), '[]'::jsonb),
        'targets', coalesce((SELECT jsonb_agg(jsonb_build_object(
            'asset', asset, 'id', id) ORDER BY asset)
            FROM quant.strategy_signals WHERE strategy='donchian_1h'
            AND exit_ts IS NULL), '[]'::jsonb),
        'dca', (SELECT jsonb_build_object('day', day, 'units', units,
            'computed_at', computed_at) FROM quant.dca_boost_days
            WHERE day=(statement_timestamp() AT TIME ZONE 'UTC')::date)
    );
$$;

REVOKE ALL ON FUNCTION api.runner_signals() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.runner_signals() TO anon, authenticated;
NOTIFY pgrst, 'reload schema';
COMMIT;
