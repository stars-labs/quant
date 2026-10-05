-- Private dispatcher projection. This function cannot read upload tokens or control execution.
BEGIN;
CREATE FUNCTION quant.operator_runner_reports(chat bigint)
RETURNS TABLE(id uuid,label text,received_at timestamptz,report jsonb)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT r.id,r.label,r.received_at,r.report
    FROM quant.runner_connections r
    WHERE r.revoked_at IS NULL AND r.venue='htx' AND r.environment='live'
      AND EXISTS (SELECT 1 FROM quant.telegram_links t
                  WHERE t.user_id=r.user_id AND t.chat_id=chat)
    ORDER BY r.received_at DESC NULLS LAST,r.created_at DESC,r.id
$$;
REVOKE ALL ON FUNCTION quant.operator_runner_reports(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION quant.operator_runner_reports(bigint) TO quant;
COMMIT;
