-- Owner-private, upload-only display connections. No exchange credentials or commands.
BEGIN;

CREATE TABLE quant.runner_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES quant.users(id) ON DELETE CASCADE,
    label text NOT NULL CHECK (length(label) BETWEEN 1 AND 64),
    venue text NOT NULL CHECK (venue IN ('htx','gate')),
    environment text NOT NULL CHECK (environment IN ('dry_run','live')),
    token_hash bytea NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    received_at timestamptz,
    sequence bigint NOT NULL DEFAULT 0,
    report jsonb
);
ALTER TABLE quant.runner_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY runner_connections_owner ON quant.runner_connections
    FOR SELECT TO authenticated USING (user_id=auth.uid());
REVOKE ALL ON quant.runner_connections FROM PUBLIC, anon, authenticated;
GRANT SELECT (id,user_id,label,venue,environment,created_at,revoked_at,
              received_at,sequence,report) ON quant.runner_connections TO authenticated;
CREATE VIEW api.runner_connections WITH (security_invoker=true) AS
    SELECT id,label,venue,environment,created_at,revoked_at,received_at,sequence,report
    FROM quant.runner_connections;
GRANT SELECT ON api.runner_connections TO authenticated;
REVOKE ALL ON api.runner_connections FROM PUBLIC, anon;

CREATE FUNCTION api.create_runner_connection(label text, venue text, environment text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE owner_id uuid := auth.uid(); upload_token text; connection_id uuid;
BEGIN
    IF owner_id IS NULL THEN RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501'; END IF;
    IF label IS NULL OR length(btrim(label)) NOT BETWEEN 1 AND 64
        OR venue IS NULL OR venue NOT IN ('htx','gate')
        OR environment IS NULL OR environment NOT IN ('dry_run','live')
    THEN RAISE EXCEPTION 'Invalid display connection'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(owner_id::text, 43));
    IF (SELECT count(*) FROM quant.runner_connections WHERE user_id=owner_id AND revoked_at IS NULL)>=5
    THEN RAISE EXCEPTION 'Maximum five active display connections'; END IF;
    upload_token := replace(gen_random_uuid()::text || gen_random_uuid()::text,'-','');
    INSERT INTO quant.runner_connections (user_id,label,venue,environment,token_hash)
        VALUES (owner_id,btrim(label),venue,environment,sha256(convert_to(upload_token,'UTF8')))
        RETURNING id INTO connection_id;
    RETURN jsonb_build_object('id',connection_id,'upload_token',upload_token);
END;
$$;

CREATE FUNCTION api.revoke_runner_connection(connection_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Authentication required' USING ERRCODE='42501'; END IF;
    UPDATE quant.runner_connections SET revoked_at=coalesce(revoked_at,now())
        WHERE id=connection_id AND user_id=auth.uid();
    RETURN FOUND;
END;
$$;

CREATE FUNCTION quant.validate_runner_report(report jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE item jsonb; k text; n numeric; stamp timestamptz;
BEGIN
    IF report IS NULL OR jsonb_typeof(report)<>'object' OR octet_length(report::text)>65536
        OR NOT (report ?& ARRAY['version','sequence','observed_at','status','venue','environment',
            'cash_usdt','equity_usdt','funded_usdt','trend_available_usdt','dca_available_usdt',
            'fees_usdt','positions','fills'])
        OR (report - ARRAY['version','sequence','observed_at','status','venue','environment',
            'cash_usdt','equity_usdt','funded_usdt','trend_available_usdt','dca_available_usdt',
            'fees_usdt','positions','fills'])<>'{}'::jsonb
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

CREATE FUNCTION api.upload_runner_report(upload_token text, report jsonb) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE connection quant.runner_connections; incoming bigint;
BEGIN
    IF upload_token IS NULL OR upload_token !~ '^[a-f0-9]{64}$'
    THEN RAISE EXCEPTION 'Invalid reporting token' USING ERRCODE='42501'; END IF;
    SELECT * INTO connection FROM quant.runner_connections
        WHERE token_hash=sha256(convert_to(upload_token,'UTF8')) AND revoked_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Invalid reporting token' USING ERRCODE='42501'; END IF;
    PERFORM quant.validate_runner_report(report);
    IF report->>'venue' IS DISTINCT FROM connection.venue
        OR report->>'environment' IS DISTINCT FROM connection.environment
    THEN RAISE EXCEPTION 'Connection identity mismatch'; END IF;
    incoming := (report->>'sequence')::bigint;
    IF incoming=connection.sequence AND report=connection.report THEN RETURN 'already_received'; END IF;
    IF incoming<=connection.sequence THEN RAISE EXCEPTION 'Report sequence must increase'; END IF;
    UPDATE quant.runner_connections SET report=upload_runner_report.report,
        sequence=incoming,received_at=now() WHERE id=connection.id;
    RETURN 'accepted';
END;
$$;

REVOKE ALL ON FUNCTION quant.validate_runner_report(jsonb) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION api.create_runner_connection(text,text,text) FROM PUBLIC,anon;
REVOKE ALL ON FUNCTION api.revoke_runner_connection(uuid) FROM PUBLIC,anon;
REVOKE ALL ON FUNCTION api.upload_runner_report(text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.create_runner_connection(text,text,text),
    api.revoke_runner_connection(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION api.upload_runner_report(text,jsonb) TO anon,authenticated;
NOTIFY pgrst, 'reload schema';
COMMIT;
