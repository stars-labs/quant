"""
Operator Telegram alerts (TELEGRAM_CHAT_ID — the operator chat, not users; user pushes are
alert_dispatcher.py).

1. KOL alerts (--kol / --all, every 30 min via quant-alerts.timer): Google-News KOL
   headlines scored by kol_tracker.py.
2. Daily report (--daily, quant-daily-report.timer): house strategy record
   (quant.strategy_record), growth funnel + the Telegram loop (quant.web_events campaigns,
   binds, weekly-active subscribers, follows — migration 037), top headlines.

Removed 2026-09-27 (dead sources): the sentiment block / sentiment-shift alert
(sentiment_data/latest_sentiment.json last written 2026-04-23), the Supabase
sentiment_snapshots trend (project host no longer resolves) and the Kelly block
(retired freqtrade HonestTrend* backtests, last 2026-04-20).
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from strategy_record import STRATEGY

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("alerts")

# Load from env or SOPS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PROJECT_DIR = Path(__file__).parent.parent

# State file to track what we've already alerted on
STATE_FILE = PROJECT_DIR / "sentiment_data" / "alert_state.json"


def send_telegram(message: str) -> bool:
    """Send a message via Telegram bot."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        # Try loading from SOPS
        _load_telegram_from_sops()

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        # requests puts the full URL (bot token included) in its message — never log it.
        logger.warning(f"Telegram send failed: {str(e).replace(TELEGRAM_TOKEN, '<token>')}")
        return False


def _load_telegram_from_sops():
    """Try to load Telegram credentials from SOPS."""
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    try:
        result = subprocess.run(
            ["sops", "decrypt", str(PROJECT_DIR / "secrets.yaml")],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import yaml
            secrets = yaml.safe_load(result.stdout)
            TELEGRAM_TOKEN = secrets.get("telegram", {}).get("bot_token", "")
            TELEGRAM_CHAT_ID = secrets.get("telegram", {}).get("chat_id", "")
    except Exception:
        pass


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_kol_hashes": [], "last_combined_score": 0.0, "last_check": ""}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# --------------------------------------------------------------------------
# Alert 1: KOL Events
# --------------------------------------------------------------------------
def check_kol_alerts():
    """Check for new high-impact KOL events and alert."""
    from kol_tracker import KOLTracker

    state = load_state()
    seen = set(state.get("last_kol_hashes", []))

    tracker = KOLTracker()
    result = tracker.run()

    new_alerts = []
    new_hashes = []

    for m in result.get("kol_mentions", []):
        # Only alert on significant mentions
        if abs(m.get("score", 0)) < 0.3:
            continue

        # Deduplicate by title hash
        import hashlib
        h = hashlib.sha256(m["title"].lower().strip().encode()).hexdigest()[:16]
        new_hashes.append(h)

        if h in seen:
            continue

        icon = "🟢" if m["score"] > 0 else "🔴"
        title = m["title"][:140]
        # Escape Markdown special chars in title (underscores, asterisks, brackets)
        for ch in ("_", "*", "[", "]", "`"):
            title = title.replace(ch, f"\\{ch}")
        link = m.get("link", "").strip()
        if link:
            # Markdown inline link: [title](url) — user can tap to verify original
            title_line = f"[{title}]({link})"
        else:
            title_line = title
        new_alerts.append(
            f"{icon} *{m['kol'].upper()}* ({m['score']:+.2f})\n{title_line}"
        )

    if new_alerts:
        header = f"*KOL Alert* ({len(new_alerts)} new events)\n{'─' * 30}\n"
        message = header + "\n\n".join(new_alerts[:5])  # max 5 per alert
        send_telegram(message)
        logger.info(f"Sent {len(new_alerts)} KOL alerts")

    # Update state
    state["last_kol_hashes"] = new_hashes[-50:]  # keep last 50
    save_state(state)

    return len(new_alerts)


# --------------------------------------------------------------------------
# Helper: house strategy record (quant.strategy_record, migration 032)
# --------------------------------------------------------------------------
# The public track record of the house trend rule (趋势突破策略, Donchian 1h 168/72 on
# sr.ASSETS). quant.strategy_record is the single source of truth for its stats; this
# block only does the cross-asset roll-up every consumer does (equal-weight averages,
# pooled win rate). Bar timestamps are Binance close times (hh:59:59.999) → shown as the
# round hour they close at, UTC.
def _bar_utc(ts: datetime) -> datetime:
    return (ts + timedelta(milliseconds=1)).astimezone(timezone.utc)


def format_strategy_block(record: list[dict]) -> str:
    """Compact English 'Strategy record' block (Markdown) from quant.strategy_record rows.

    Per asset: long +x% (open position marked to market, net of fees; backfilled entries
    labelled) or flat (+y% to the breakout trigger). Then portfolio vs buy-and-hold since
    the record start, closed trades and win rate. Empty string when there are no rows.
    """
    if not record:
        return ""
    lines = []
    for r in record:
        if r["open_entry_ts"] is not None:
            src = "" if r["open_live"] else ", backfilled"
            lines.append(f"  {r['asset']}: long {r['open_ret']:+.1%} "
                         f"(since {_bar_utc(r['open_entry_ts']):%m-%d}{src})")
        elif r["channel_high"] is not None and r["last_close"]:
            lines.append(f"  {r['asset']}: flat "
                         f"({r['channel_high'] / r['last_close'] - 1:+.1%} to trigger)")
        else:
            lines.append(f"  {r['asset']}: flat")
    priced = [r for r in record if r["sleeve_ret"] is not None and r["hold_ret"] is not None]
    if priced:
        ret = sum(r["sleeve_ret"] for r in priced) / len(priced)
        hold = sum(r["hold_ret"] for r in priced) / len(priced)
        starts = [r["start_ts"] for r in priced if r["start_ts"] is not None]
        since = f" since {_bar_utc(min(starts)):%Y-%m-%d}" if starts else ""
        lines.append(f"  Portfolio {ret:+.1%} vs hold {hold:+.1%}{since}")
    n_closed = sum(r["n_closed"] for r in record)
    n_wins = sum(r["n_wins"] for r in record)
    lines.append(f"  Trades: {n_closed} closed, win rate {n_wins / n_closed:.0%}"
                 if n_closed else "  Trades: none closed yet")
    lasts = [r["last_ts"] for r in record if r["last_ts"] is not None]
    asof = f" (last bar {_bar_utc(max(lasts)):%m-%d %H:%M} UTC)" if lasts else ""
    return f"\n*Strategy record*{asof}:\n" + "\n".join(lines)


def strategy_record_block(timescale_url: str) -> str:
    """Query quant.strategy_record and format it; "" when the DB isn't configured or fails."""
    if psycopg2 is None or not timescale_url:
        return ""
    try:
        conn = psycopg2.connect(timescale_url)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM quant.strategy_record WHERE strategy = %s ORDER BY asset",
                            (STRATEGY,))
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"strategy record query failed: {e}")
        return ""
    return format_strategy_block(rows)


# --------------------------------------------------------------------------
# Growth: funnel + the Telegram loop (quant.web_events, telegram_links, user_follows)
# --------------------------------------------------------------------------
# Every dispatcher link carries ?ref=<channel>; the web stores it in web_events.campaign
# (landing page_view = that URL's ref; conversions = the browser's first-touch ref).
GROWTH_SQL = {
    "funnel": """
        WITH yest AS (SELECT * FROM quant.web_events WHERE ts >= now() - interval '24 hours')
        SELECT
          (SELECT count(DISTINCT visitor) FROM yest WHERE event = 'page_view') AS visitors,
          (SELECT count(*) FROM yest WHERE event = 'page_view')                AS views,
          (SELECT count(*) FROM yest WHERE event = 'signup')                   AS signups,
          (SELECT count(*) FROM yest WHERE event = 'backtest_submit')          AS backtests,
          (SELECT count(*) FROM yest WHERE event = 'signal_create')            AS signals,
          -- D1 return: visitors seen in the last 24h AND in the 24h before
          (SELECT count(DISTINCT y.visitor) FROM yest y
            WHERE EXISTS (SELECT 1 FROM quant.web_events p
                           WHERE p.visitor = y.visitor
                             AND p.ts >= now() - interval '48 hours'
                             AND p.ts <  now() - interval '24 hours'))        AS d1_return""",
    "visits": """
        SELECT campaign,
               count(DISTINCT visitor) FILTER (WHERE ts >= now() - interval '24 hours') AS d1,
               count(DISTINCT visitor)                                                AS d7
          FROM quant.web_events
         WHERE event = 'page_view' AND campaign IS NOT NULL AND ts >= now() - interval '7 days'
         GROUP BY campaign ORDER BY d7 DESC, campaign""",
    "binds": """
        SELECT count(*) FILTER (WHERE bound_at >= now() - interval '24 hours') AS d1,
               count(*) FILTER (WHERE bound_at >= now() - interval '7 days')   AS d7,
               count(*)                                                        AS bound,
               count(*) FILTER (WHERE last_seen_at >= now() - interval '7 days'
                                   OR EXISTS (SELECT 1 FROM quant.web_events e
                                               WHERE e.user_id = l.user_id
                                                 AND e.ts >= now() - interval '7 days')) AS wau
          FROM quant.telegram_links l
         WHERE chat_id IS NOT NULL""",
    "bind_refs": """
        SELECT coalesce(campaign, 'direct') AS campaign,
               count(DISTINCT coalesce(user_id::text, visitor)) AS n
          FROM quant.web_events
         WHERE event = 'telegram_bound' AND ts >= now() - interval '7 days'
         GROUP BY 1 ORDER BY n DESC, 1""",
    "follows": """
        SELECT count(*) FILTER (WHERE followed_at >= now() - interval '24 hours') AS d1,
               count(*) FILTER (WHERE followed_at >= now() - interval '7 days')   AS d7
          FROM quant.user_follows""",
}


def _code(s: str) -> str:
    """Campaign names have underscores — Markdown italics unless code-quoted."""
    return f"`{s}`"


def format_growth_block(g: dict) -> str:
    """Markdown growth block from growth_stats() output (keys of GROWTH_SQL)."""
    f = g["funnel"]
    lines = [
        "\n*Growth (24h):*",
        f"  Visitors: {f['visitors']}  |  Views: {f['views']}  |  D1 return: {f['d1_return']}",
        f"  Signups: {f['signups']}  |  Backtests: {f['backtests']}  |  Signals: {f['signals']}",
        "*Telegram loop (24h / 7d):*",
    ]
    visits = ", ".join(f"{_code(v['campaign'])} {v['d1']}/{v['d7']}" for v in g["visits"])
    lines.append(f"  Visits by ref: {visits or 'none'}")
    b = g["binds"]
    refs = ", ".join(f"{_code(r['campaign'])} {r['n']}" for r in g["bind_refs"])
    lines.append(f"  New binds: {b['d1']}/{b['d7']}" + (f" (7d by first ref: {refs})" if refs else ""))
    lines.append(f"  Subscribers: {b['bound']} bound, {b['wau']} active this week")
    fo = g["follows"]
    lines.append(f"  Follows: {fo['d1']}/{fo['d7']}")
    return "\n".join(lines)


def growth_stats(conn) -> dict:
    out = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for key, sql in GROWTH_SQL.items():
            cur.execute(sql)
            out[key] = cur.fetchall() if key in ("visits", "bind_refs") else cur.fetchone()
    return out


def growth_block(timescale_url: str) -> str:
    if psycopg2 is None or not timescale_url:
        return ""
    try:
        conn = psycopg2.connect(timescale_url)
        try:
            return format_growth_block(growth_stats(conn))
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"growth query failed: {e}")
        return ""


def news_block(timescale_url: str) -> str:
    """Top headlines of the last 24h (quant.news_items): Fed/SEC/ECB first, then freshest."""
    if psycopg2 is None or not timescale_url:
        return ""
    try:
        conn = psycopg2.connect(timescale_url)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT source, title
                    FROM quant.news_items
                    WHERE published_at >= now() - interval '24 hours'
                    ORDER BY CASE WHEN source IN ('Fed','SEC','ECB') THEN 0 ELSE 1 END,
                             published_at DESC
                    LIMIT 5
                """)
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"news query failed: {e}")
        return ""
    if not rows:
        return ""
    return "\n*Market wire (24h):*\n" + "\n".join(
        f"  • [{src}] {(title or '')[:80]}" for src, title in rows)


# --------------------------------------------------------------------------
# Daily Report
# --------------------------------------------------------------------------
def send_daily_report():
    """Once per UTC day: strategy record + growth / Telegram loop + headlines."""
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("last_daily_report", "") == today:
        logger.info("Daily report already sent today")
        return

    timescale_url = os.environ.get("TIMESCALE_URL", "")
    message = (f"*Daily Report* 📊 {today}\n" + "─" * 30
               + strategy_record_block(timescale_url)
               + growth_block(timescale_url)
               + news_block(timescale_url))
    send_telegram(message)
    logger.info("Daily report sent")

    state["last_daily_report"] = today
    save_state(state)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--kol", action="store_true", help="Check KOL alerts only")
    parser.add_argument("--daily", action="store_true", help="Send daily report")
    parser.add_argument("--all", action="store_true", help="Run all checks (default)")
    args = parser.parse_args()

    if args.kol or args.all or not args.daily:
        n = check_kol_alerts()
        print(f"KOL alerts: {n} new")

    if args.daily:
        send_daily_report()
        print("Daily report: sent")
