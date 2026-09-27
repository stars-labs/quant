-- 038: drop quant.event_dca_triggers — the event-DCA bot's trigger log.
--
-- Its only writer was the freqtrade-era event_dca_bot.py → event_dca_state.json →
-- scripts/sync_local_state_to_timescale.py; that bot was retired in the Nautilus migration and
-- the last row is from 2026-06-07. The web consumers (/live, the /dca + /signals trigger charts,
-- the home-page plan simulator's "event buys") are gone, and the Telegram 'dca_events' topic was
-- dropped in 032. What still referenced the table:
--   api.event_dca_triggers, api.public_event_triggers   views (002 / 007) — dropped here
--   quant.enqueue_weekly_digests()                        pg_cron job 1 (Mon 09:00) — plpgsql
--       reads the table at run time, so it is redefined below without the "Event DCA
--       triggers" card BEFORE the table goes (otherwise the weekly job starts failing).
--   publication supabase_realtime                         drops the table with it
--
-- Re-runnable. Apply as the api-schema owner (postgres) on oracle-arm-002:
--   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -v ON_ERROR_STOP=1" < migrations/038_drop_event_dca_triggers.sql
-- then: psql … -c "NOTIFY pgrst, 'reload schema'"

BEGIN;

CREATE OR REPLACE FUNCTION quant.enqueue_weekly_digests()
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = quant, public
AS $$
DECLARE
  v_count       int := 0;
  v_user        record;
  v_dashboard   text;
  v_btc_now     numeric;
  v_btc_prev    numeric;
  v_btc_delta   numeric;
  v_run_rows    int;
  v_subject     text;
  v_html        text;
  v_name        text;
BEGIN
  SELECT value INTO v_dashboard FROM quant.app_config WHERE key = 'dashboard_url';
  v_dashboard := COALESCE(v_dashboard, 'https://quant.panda.qzz.io');

  -- BTC % move over the past 7 days (daily close).
  SELECT close INTO v_btc_now
    FROM quant.ohlc_1d WHERE pair = 'BTC/USDT'
    ORDER BY bucket DESC LIMIT 1;
  SELECT close INTO v_btc_prev
    FROM quant.ohlc_1d WHERE pair = 'BTC/USDT' AND bucket < now() - INTERVAL '7 days'
    ORDER BY bucket DESC LIMIT 1;
  v_btc_delta := CASE WHEN v_btc_prev IS NULL OR v_btc_prev = 0 THEN 0
                      ELSE ((v_btc_now - v_btc_prev) / v_btc_prev) * 100 END;

  -- New backtest runs this week.
  SELECT count(*)::int INTO v_run_rows
    FROM quant.backtest_runs WHERE imported_at >= now() - INTERVAL '7 days';

  FOR v_user IN
    SELECT up.user_id, u.email, up.display_name
    FROM quant.user_preferences up
    JOIN quant.users u ON u.id = up.user_id
    WHERE up.email_digest = true AND u.email IS NOT NULL
  LOOP
    v_name := COALESCE(
      v_user.display_name,
      split_part(v_user.email, '@', 1)
    );
    v_subject := format(
      'Crypto Quant weekly — BTC %s%%',
      CASE WHEN v_btc_delta >= 0 THEN '+' ELSE '' END || round(v_btc_delta, 1)
    );
    v_html := format($F$
<!doctype html><html><body style="margin:0;padding:0;background:#0b0d11;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
  <table width="100%%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;padding:32px 20px;">
    <tr><td>
      <h1 style="font-size:22px;margin:0 0 6px;color:#fff;">Crypto Quant · weekly</h1>
      <p style="color:#9ca3af;font-size:13px;margin:0 0 24px;">Hi %s — here's what the bots did this week.</p>

      <table width="100%%" cellpadding="0" cellspacing="0" style="border:1px solid #1f2937;border-radius:10px;padding:20px;">
        <tr><td>
          <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.5px;">BTC · 7d</div>
          <div style="font-size:28px;font-weight:600;color:%s;margin-top:4px;">%s%% </div>
          <div style="color:#6b7280;font-size:12px;margin-top:2px;">now $%s · 7 days ago $%s</div>
        </td></tr>
      </table>

      <div style="margin-top:16px;border:1px solid #1f2937;border-radius:10px;padding:16px;">
        <div style="font-size:11px;color:#9ca3af;text-transform:uppercase;">New backtests</div>
        <div style="font-size:22px;font-weight:600;color:#fff;margin-top:4px;">%s</div>
        <div style="color:#6b7280;font-size:12px;margin-top:2px;">imported this week</div>
      </div>

      <div style="margin-top:28px;text-align:center;">
        <a href="%s" style="display:inline-block;background:#3b82f6;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:500;font-size:14px;">See the full dashboard →</a>
      </div>

      <p style="color:#6b7280;font-size:11px;margin-top:32px;text-align:center;line-height:1.5;">
        You're getting this because you opted in on /dca.<br>
        Unsubscribe: toggle the weekly digest checkbox on <a href="%s/dca" style="color:#9ca3af;">/dca</a>.
      </p>
    </td></tr>
  </table>
</body></html>
$F$,
      v_name,
      CASE WHEN v_btc_delta >= 0 THEN '#22c55e' ELSE '#ef4444' END,
      CASE WHEN v_btc_delta >= 0 THEN '+' ELSE '' END || round(v_btc_delta, 1),
      to_char(round(v_btc_now),  'FM999G999'),
      to_char(round(v_btc_prev), 'FM999G999'),
      v_run_rows,
      v_dashboard,
      v_dashboard
    );

    INSERT INTO quant.email_queue (user_id, to_email, subject, html)
    VALUES (v_user.user_id, v_user.email, v_subject, v_html);
    v_count := v_count + 1;
  END LOOP;

  RETURN v_count;
END;
$$;

DROP VIEW IF EXISTS api.public_event_triggers;
DROP VIEW IF EXISTS api.event_dca_triggers;
DROP TABLE IF EXISTS quant.event_dca_triggers;

COMMIT;
