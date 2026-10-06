-- Estimated observed-period Modified Dietz returns.
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
            'fees_usdt','positions','fills','decisions','history','attribution','funding_history','return_summary'])<>'{}'::jsonb
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
    IF report ? 'return_summary' THEN
        item := report->'return_summary';
        IF jsonb_typeof(item)<>'object'
            OR NOT (item ?& ARRAY['method','estimated','start_at','end_at','return_pct','unavailable_reason'])
            OR (item-ARRAY['method','estimated','start_at','end_at','return_pct','unavailable_reason'])<>'{}'::jsonb
            OR jsonb_typeof(item->'method')<>'string' OR item->>'method'<>'modified_dietz' OR item->'estimated'<>'true'::jsonb
        THEN RAISE EXCEPTION 'Invalid return fields'; END IF;
        FOREACH k IN ARRAY ARRAY['start_at','end_at'] LOOP
            IF item->k<>'null'::jsonb THEN
                IF jsonb_typeof(item->k)<>'string' OR (item->>k) !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
                THEN RAISE EXCEPTION 'Invalid return timestamp'; END IF;
                IF (item->>k)::timestamptz>now()+interval '30 seconds'
                THEN RAISE EXCEPTION 'Future return timestamp'; END IF;
            END IF;
        END LOOP;
        IF item->'return_pct'='null'::jsonb THEN
            IF jsonb_typeof(item->'unavailable_reason')<>'string'
                OR item->>'unavailable_reason' NOT IN ('insufficient_observations','invalid_valuation',
                    'invalid_observation_times','invalid_cash_flow','invalid_timestamps_or_amounts',
                    'unknown_flow_timing','unreconciled_cash_flows','nonpositive_capital','invalid_return')
            THEN RAISE EXCEPTION 'Invalid unavailable return'; END IF;
        ELSE
            IF jsonb_typeof(item->'return_pct')<>'number' OR (item->>'return_pct')::numeric NOT BETWEEN -1000000000000 AND 1000000000000
                OR item->'unavailable_reason'<>'null'::jsonb
                OR item->'start_at'='null'::jsonb OR item->'end_at'='null'::jsonb
                OR (item->>'end_at')::timestamptz<=(item->>'start_at')::timestamptz
            THEN RAISE EXCEPTION 'Invalid estimated return'; END IF;
        END IF;
    END IF;
    IF report ? 'funding_history' THEN
        IF jsonb_typeof(report->'funding_history')<>'array' OR jsonb_array_length(report->'funding_history')>100
        THEN RAISE EXCEPTION 'Invalid funding history'; END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(report->'funding_history') LOOP
            IF jsonb_typeof(item)<>'object'
                OR NOT (item ?& ARRAY['reference','month','kind','confirmed_at','trend_delta_usdt','dca_delta_usdt','cash_delta_usdt'])
                OR (item-ARRAY['reference','month','kind','confirmed_at','trend_delta_usdt','dca_delta_usdt','cash_delta_usdt'])<>'{}'::jsonb
                OR jsonb_typeof(item->'reference')<>'string' OR item->>'reference' !~ '^[A-Za-z0-9:_-]{1,128}$'
                OR jsonb_typeof(item->'month')<>'string' OR item->>'month' !~ '^[0-9]{4}-[0-9]{2}-01$'
                OR jsonb_typeof(item->'kind')<>'string' OR item->>'kind' NOT IN ('deposit','withdrawal','allocation','carry')
            THEN RAISE EXCEPTION 'Invalid funding history fields'; END IF;
            PERFORM (item->>'month')::date;
            IF item->'confirmed_at'<>'null'::jsonb THEN
                IF jsonb_typeof(item->'confirmed_at')<>'string' OR item->>'confirmed_at' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
                THEN RAISE EXCEPTION 'Invalid confirmation time'; END IF;
                IF (item->>'confirmed_at')::timestamptz>now()+interval '30 seconds'
                THEN RAISE EXCEPTION 'Future confirmation'; END IF;
            END IF;
            FOREACH k IN ARRAY ARRAY['trend_delta_usdt','dca_delta_usdt','cash_delta_usdt'] LOOP
                IF jsonb_typeof(item->k)<>'number' OR (item->>k)::numeric NOT BETWEEN -1000000000000 AND 1000000000000
                THEN RAISE EXCEPTION 'Invalid cash movement'; END IF;
            END LOOP;
            n := (item->>'cash_delta_usdt')::numeric;
            IF (item->>'kind'<>'carry' AND abs(n-(item->>'trend_delta_usdt')::numeric-(item->>'dca_delta_usdt')::numeric)>0.000001)
                OR (item->>'kind'='deposit' AND n<=0) OR (item->>'kind'='withdrawal' AND n>=0)
                OR (item->>'kind'='allocation' AND n<>0)
                OR (item->>'kind'='carry' AND (n<>0 OR (item->>'trend_delta_usdt')::numeric<>0 OR (item->>'dca_delta_usdt')::numeric=0))
            THEN RAISE EXCEPTION 'Funding movement mismatch'; END IF;
        END LOOP;
    END IF;
    IF report ? 'attribution' THEN
        IF jsonb_typeof(report->'attribution')<>'array' OR jsonb_array_length(report->'attribution')>100
        THEN RAISE EXCEPTION 'Invalid attribution list'; END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(report->'attribution') LOOP
            IF jsonb_typeof(item)<>'object'
                OR NOT (item ?& ARRAY['strategy','asset','realized_pnl_usdt','unrealized_pnl_usdt','net_pnl_usdt','fees_usdt'])
                OR (item-ARRAY['strategy','asset','realized_pnl_usdt','unrealized_pnl_usdt','net_pnl_usdt','fees_usdt'])<>'{}'::jsonb
                OR jsonb_typeof(item->'strategy')<>'string' OR item->>'strategy' NOT IN ('trend','dca')
                OR jsonb_typeof(item->'asset')<>'string' OR item->>'asset' !~ '^[A-Z0-9]{2,20}$'
            THEN RAISE EXCEPTION 'Invalid attribution fields'; END IF;
            FOREACH k IN ARRAY ARRAY['realized_pnl_usdt','unrealized_pnl_usdt','net_pnl_usdt','fees_usdt'] LOOP
                IF jsonb_typeof(item->k)<>'number' OR (item->>k)::numeric NOT BETWEEN -1000000000000 AND 1000000000000
                    OR (k='fees_usdt' AND (item->>k)::numeric<0)
                THEN RAISE EXCEPTION 'Invalid attribution amount'; END IF;
            END LOOP;
            IF abs((item->>'net_pnl_usdt')::numeric-(item->>'realized_pnl_usdt')::numeric-(item->>'unrealized_pnl_usdt')::numeric)>0.000001
            THEN RAISE EXCEPTION 'Attribution PnL mismatch'; END IF;
        END LOOP;
        IF (SELECT count(DISTINCT (a->>'strategy')||':'||(a->>'asset')) FROM jsonb_array_elements(report->'attribution') a)<>jsonb_array_length(report->'attribution')
        THEN RAISE EXCEPTION 'Duplicate attribution asset'; END IF;
        IF abs((SELECT coalesce(sum((a->>'net_pnl_usdt')::numeric),0) FROM jsonb_array_elements(report->'attribution') a)
            -((report->>'equity_usdt')::numeric-(report->>'funded_usdt')::numeric))>0.000001
            OR abs((SELECT coalesce(sum((a->>'fees_usdt')::numeric),0) FROM jsonb_array_elements(report->'attribution') a)
            -(report->>'fees_usdt')::numeric)>0.000001
        THEN RAISE EXCEPTION 'Attribution totals disagree with account'; END IF;
    END IF;
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
    IF report ? 'history' AND (SELECT count(DISTINCT a->>'observed_at') FROM jsonb_array_elements(report->'history') a)<>jsonb_array_length(report->'history')
    THEN RAISE EXCEPTION 'Duplicate history timestamp'; END IF;
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
