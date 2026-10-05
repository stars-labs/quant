-- Retire hosted exchange credential custody. Apply after deploying endpoint removal.
BEGIN;
DROP VIEW api.user_preferences;
ALTER TABLE quant.user_preferences
    DROP COLUMN binance_api_key,
    DROP COLUMN binance_api_secret,
    DROP COLUMN binance_connected_at;
CREATE VIEW api.user_preferences WITH (security_invoker=true) AS
    SELECT user_id,dca_plan,email_digest,display_name,updated_at FROM quant.user_preferences;
GRANT SELECT,INSERT,UPDATE ON api.user_preferences TO authenticated,service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
