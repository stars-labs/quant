-- Private bound-user report queries and opt-in delivery through the existing dispatcher.
BEGIN;
ALTER FUNCTION quant.operator_runner_reports(bigint) RENAME TO private_runner_reports;
CREATE TABLE quant.runner_alert_subscriptions (
    chat_id bigint PRIMARY KEY, user_id uuid NOT NULL REFERENCES quant.users(id) ON DELETE CASCADE,
    enabled boolean NOT NULL DEFAULT false
);
REVOKE ALL ON quant.runner_alert_subscriptions FROM PUBLIC,anon,authenticated,quant;
CREATE FUNCTION quant.set_runner_alerts(chat bigint, enabled boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE owner uuid;
BEGIN
    SELECT t.user_id INTO owner FROM quant.telegram_links t
    WHERE t.chat_id=chat AND EXISTS (SELECT 1 FROM quant.runner_connections r
        WHERE r.user_id=t.user_id AND r.revoked_at IS NULL AND r.environment='live' AND r.venue='htx');
    IF owner IS NULL THEN RETURN false; END IF;
    INSERT INTO quant.runner_alert_subscriptions(chat_id,user_id,enabled) VALUES(chat,owner,enabled)
    ON CONFLICT(chat_id) DO UPDATE SET user_id=excluded.user_id,enabled=excluded.enabled;
    RETURN true;
END;
$$;
CREATE FUNCTION quant.runner_alert_chats() RETURNS SETOF bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT s.chat_id FROM quant.runner_alert_subscriptions s
    WHERE s.enabled AND EXISTS (SELECT 1 FROM quant.telegram_links t
        WHERE t.chat_id=s.chat_id AND t.user_id=s.user_id)
      AND EXISTS (SELECT 1 FROM quant.runner_connections r
        WHERE r.user_id=s.user_id AND r.revoked_at IS NULL AND r.environment='live' AND r.venue='htx')
$$;
REVOKE ALL ON FUNCTION quant.set_runner_alerts(bigint,boolean),quant.runner_alert_chats() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION quant.set_runner_alerts(bigint,boolean),quant.runner_alert_chats() TO quant;
CREATE FUNCTION quant.runner_alert_setting(chat bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT enabled FROM quant.runner_alert_subscriptions WHERE chat_id=chat
$$;
REVOKE ALL ON FUNCTION quant.runner_alert_setting(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION quant.runner_alert_setting(bigint) TO quant;
COMMIT;
