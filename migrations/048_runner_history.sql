-- Private timestamped account valuation history.
BEGIN;
CREATE OR REPLACE FUNCTION quant.validate_runner_report(report jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE item jsonb; k text; n numeric; stamp timestamptz;
BEGIN
    IF report IS NULL OR jsonb_typeof(report)<>'object' OR octet_length(report::text)>131072
        OR NOT (report ?& ARRAY['version','sequence','observed_at','status','venue','environment',
            'cash_usdt','equity_usdt','funded_usdt','trend_available_usdt','dca_available_usdt',
            'fees_usdt','positions','fills'])
        OR (report - ARRAY['version','sequence','observed_at','status','venue','environment',
            'cash_usdt','equity_usdt','funded_usdt','trend_available_usdt','dca_available_usdt',
            'fees_usdt','positions','fills','decisions','history'])<>'{}'::jsonb
    THEN RAISE EXCEPTION 'Invalid report fields'; END IF;
    IF report->'version'<>'1'::jsonb OR jsonb_typeof(report->'sequence')<>'number'
        OR (report->>'sequence')::numeric NOT BETWEEN 1 AND 9007199254740991
        OR (report->>'sequence')::numeric<>trunc((report->>'sequence')::numeric)
        OR report->>'status' NOT IN ('healthy','paused','pending','stale')
        OR jsonb_typeof(report->'status')<>'string'
        OR jsonb_typeof(report->'observed_at')<>'string'
        OR (report->>'observed_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
    THEN RAISE EXCEPTION 'Invalid report metadata'; END IF;
    stamp := (report->>'observed_at')::timestamptz;
    IF stamp<now()-interval '10 minutes' OR stamp>now()+interval '30 seconds'
    THEN RAISE EXCEPTION 'Report timestamp outside allowed window'; END IF;
    FOREACH k IN ARRAY ARRAY['cash_usdt','equity_usdt','funded_usdt',
        'trend_available_usdt','dca_available_usdt','fees_usdt'] LOOP
        IF jsonb_typeof(report->k)<>'number' OR (report->>k)::numeric NOT BETWEEN 0 AND 1000000000000
        THEN RAISE EXCEPTION 'Invalid report amount'; END IF;
    END LOOP;
    IF jsonb_typeof(report->'positions')<>'array' OR jsonb_array_length(report->'positions')>100
        OR jsonb_typeof(report->'fills')<>'array' OR jsonb_array_length(report->'fills')>50
    THEN RAISE EXCEPTION 'Invalid report lists'; END IF;
    IF report ? 'history' THEN
        IF jsonb_typeof(report->'history')<>'array' OR jsonb_array_length(report->'history')>168
        THEN RAISE EXCEPTION 'Invalid history list'; END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(report->'history') LOOP
            IF jsonb_typeof(item)<>'object'
                OR NOT (item ?& ARRAY['observed_at','price_as_of','equity_usdt','cash_usdt','net_contributions_usdt','fees_usdt','net_pnl_usdt'])
                OR (item-ARRAY['observed_at','price_as_of','equity_usdt','cash_usdt','net_contributions_usdt','fees_usdt','net_pnl_usdt'])<>'{}'::jsonb
            THEN RAISE EXCEPTION 'Invalid history fields'; END IF;
            FOREACH k IN ARRAY ARRAY['observed_at','price_as_of'] LOOP
                IF jsonb_typeof(item->k)<>'string' OR (item->>k) !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
                THEN RAISE EXCEPTION 'Invalid history timestamp'; END IF;
                stamp := (item->>k)::timestamptz;
                IF stamp>now()+interval '30 seconds' THEN RAISE EXCEPTION 'Future history'; END IF;
            END LOOP;
            IF (item->>'price_as_of')::timestamptz>(item->>'observed_at')::timestamptz
                OR (item->>'observed_at')::timestamptz-(item->>'price_as_of')::timestamptz>interval '3 hours 30 seconds'
            THEN RAISE EXCEPTION 'Invalid history valuation age'; END IF;
            FOREACH k IN ARRAY ARRAY['equity_usdt','cash_usdt','net_contributions_usdt','fees_usdt','net_pnl_usdt'] LOOP
                IF jsonb_typeof(item->k)<>'number' OR (item->>k)::numeric NOT BETWEEN -1000000000000 AND 1000000000000
                    OR (k<>'net_pnl_usdt' AND (item->>k)::numeric<0)
                THEN RAISE EXCEPTION 'Invalid history amount'; END IF;
            END LOOP;
            IF abs((item->>'net_pnl_usdt')::numeric-((item->>'equity_usdt')::numeric-(item->>'net_contributions_usdt')::numeric))>0.000001
            THEN RAISE EXCEPTION 'History PnL mismatch'; END IF;
        END LOOP;
    END IF;
    IF report ? 'decisions' THEN
        IF jsonb_typeof(report->'decisions')<>'array' OR jsonb_array_length(report->'decisions')>100
        THEN RAISE EXCEPTION 'Invalid decision list'; END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(report->'decisions') LOOP
            IF jsonb_typeof(item)<>'object'
                OR NOT (item ?& ARRAY['strategy','asset','reason'])
                OR (item-ARRAY['strategy','asset','reason'])<>'{}'::jsonb
                OR jsonb_typeof(item->'strategy')<>'string'
                OR item->>'strategy' NOT IN ('account','trend','dca')
                OR NOT (item->'asset'='null'::jsonb OR
                    (jsonb_typeof(item->'asset')='string' AND item->>'asset' ~ '^[A-Z0-9]{2,20}$'))
                OR jsonb_typeof(item->'reason')<>'string'
                OR item->>'reason' NOT IN ('pending_reconciliation','exit_submitted','entry_submitted',
                    'below_exchange_minimum','no_entry_signal','target_already_processed',
                    'confirmed_budget_unavailable','entries_disabled','no_dca_signal',
                    'today_already_processed','reconciliation_failed','signal_feed_failed','execution_failed')
            THEN RAISE EXCEPTION 'Invalid decision fields'; END IF;
        END LOOP;
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(report->'positions') LOOP
        IF jsonb_typeof(item)<>'object'
            OR NOT (item ?& ARRAY['strategy','asset','quantity','price_usdt','cost_usdt','realized_pnl_usdt'])
            OR (item-ARRAY['strategy','asset','quantity','price_usdt','cost_usdt','realized_pnl_usdt'])<>'{}'::jsonb
            OR item->>'strategy' NOT IN ('trend','dca') OR jsonb_typeof(item->'strategy')<>'string'
            OR jsonb_typeof(item->'asset')<>'string' OR item->>'asset' !~ '^[A-Z0-9]{2,20}$'
        THEN RAISE EXCEPTION 'Invalid position fields'; END IF;
        FOREACH k IN ARRAY ARRAY['quantity','price_usdt','cost_usdt','realized_pnl_usdt'] LOOP
            IF jsonb_typeof(item->k)<>'number' THEN RAISE EXCEPTION 'Invalid position amount'; END IF;
            n := (item->>k)::numeric;
            IF n NOT BETWEEN -1000000000000 AND 1000000000000 OR (k<>'realized_pnl_usdt' AND n<0)
            THEN RAISE EXCEPTION 'Invalid position amount'; END IF;
        END LOOP;
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(report->'fills') LOOP
        IF jsonb_typeof(item)<>'object'
            OR NOT (item ?& ARRAY['client_id','strategy','asset','side','quantity','quote_usdt','fee_usdt','fee_rate','finished_at'])
            OR (item-ARRAY['client_id','strategy','asset','side','quantity','quote_usdt','fee_usdt','fee_rate','finished_at'])<>'{}'::jsonb
            OR jsonb_typeof(item->'client_id')<>'string' OR item->>'client_id' !~ '^[A-Za-z0-9:_-]{1,128}$'
            OR jsonb_typeof(item->'strategy')<>'string' OR item->>'strategy' NOT IN ('trend','dca')
            OR jsonb_typeof(item->'asset')<>'string' OR item->>'asset' !~ '^[A-Z0-9]{2,20}$'
            OR jsonb_typeof(item->'side')<>'string' OR item->>'side' NOT IN ('buy','sell')
            OR jsonb_typeof(item->'finished_at')<>'string'
            OR (item->>'finished_at') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
        THEN RAISE EXCEPTION 'Invalid fill fields'; END IF;
        stamp := (item->>'finished_at')::timestamptz;
        IF stamp>now()+interval '30 seconds' THEN RAISE EXCEPTION 'Invalid fill timestamp'; END IF;
        FOREACH k IN ARRAY ARRAY['quantity','quote_usdt','fee_usdt','fee_rate'] LOOP
            IF jsonb_typeof(item->k)<>'number' OR (item->>k)::numeric NOT BETWEEN 0 AND 1000000000000
            THEN RAISE EXCEPTION 'Invalid fill amount'; END IF;
        END LOOP;
        IF (item->>'fee_rate')::numeric>0.003 THEN RAISE EXCEPTION 'Invalid fill fee'; END IF;
    END LOOP;
END;
$$;

NOTIFY pgrst, 'reload schema';
COMMIT;
