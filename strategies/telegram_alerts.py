"""
Telegram Alert System

1. KOL real-time alerts — when Trump/Musk/BlackRock moves, get notified fast
2. Sentiment shift alerts — when combined_score changes significantly
3. Daily report — market + house strategy record (quant.strategy_record) + Kelly verdicts

Run every 30 min via systemd timer (separate from the 4-hour pipeline).
"""

import json
import logging
import os
import subprocess
import sys
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
# Alert 2: Sentiment Shift
# --------------------------------------------------------------------------
def check_sentiment_shift():
    """Alert when combined_score changes significantly."""
    state = load_state()
    last_score = state.get("last_combined_score", 0.0)

    # Read latest
    sentiment_file = PROJECT_DIR / "sentiment_data" / "latest_sentiment.json"
    try:
        with open(sentiment_file) as f:
            data = json.loads(f.read())
        current_score = data.get("combined_score", 0.0)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    delta = current_score - last_score

    # Alert on significant shifts (> 0.2 change)
    if abs(delta) > 0.2:
        direction = "📈 BULLISH" if delta > 0 else "📉 BEARISH"
        message = (
            f"*Sentiment Shift* {direction}\n"
            f"{'─' * 30}\n"
            f"Score: {last_score:+.2f} → *{current_score:+.2f}* ({delta:+.2f})\n"
            f"FnG: {data.get('fng_value', '?')} ({data.get('fng_classification', '?')})\n"
            f"KOL: {data.get('kol_score', 0):+.2f} ({data.get('kol_mentions', 0)} mentions)\n"
            f"Signal: *{data.get('signal', '?').upper()}*"
        )
        send_telegram(message)
        logger.info(f"Sentiment shift alert: {last_score:+.2f} → {current_score:+.2f}")

    # Also alert on regime change
    if current_score > 0.3 and last_score <= 0.3:
        send_telegram("*Regime Change*: → BULLISH 🟢\nSentiment crossed above +0.3 threshold")
    elif current_score < -0.3 and last_score >= -0.3:
        send_telegram("*Regime Change*: → BEARISH 🔴\nSentiment crossed below -0.3 threshold")

    state["last_combined_score"] = current_score
    save_state(state)


# --------------------------------------------------------------------------
# Helper: per-strategy Kelly verdict
# --------------------------------------------------------------------------
# The Kelly sizer (strategies/kelly_sizer.py) lazy-loads per-strategy stats
# during bot_loop_start; once that's done they live only in the bot process
# memory. This helper recomputes the same stats on demand so the daily
# Telegram report and the --kelly CLI can both surface them.
_KELLY_TRACKED_STRATEGIES = [
    "HonestTrend15mDry",
    "HonestTrend15mProtections",
    "HonestTrend1mLive",
    "HonestTrend1mMTF",
    "HonestTrendFutures",
]


def kelly_status_dict() -> dict:
    """Return Kelly status for tracked strategies as a serialisable dict.

    Shape (one entry per strategy):
      {
        "generated_at": "2026-05-13T09:30:00Z",
        "min_trades_for_kelly": 30,
        "wilson_z": 1.96,
        "strategies": [
          {"name": "...", "status": "ok|negative_edge|insufficient_n|no_data",
           "win_rate": 0.33, "payoff_ratio": 2.18, "n_trades": 570,
           "f_half_point": 0.0125, "f_half_shrunk": 0.0, "verdict": "<text>"}
        ]
      }

    This is the machine-readable counterpart of format_kelly_report() — same
    underlying data, useful for dashboards, monitoring, or piping to jq.
    """
    sys.path.insert(0, str(PROJECT_DIR / "strategies"))
    try:
        from kelly_sizer import (
            MIN_TRADES_FOR_KELLY,
            WILSON_Z,
            latest_strategy_stats,
        )
    except Exception as e:
        logger.debug(f"Kelly status skipped (import failed): {e}")
        return {"error": f"import failed: {e}", "strategies": []}

    strategies = []
    for name in _KELLY_TRACKED_STRATEGIES:
        entry: dict = {"name": name}
        try:
            stats = latest_strategy_stats(name)
        except Exception as e:
            stats = None
            entry["error"] = str(e)
        if stats is None:
            entry["status"] = "no_data"
            entry["verdict"] = "no recent backtest"
            strategies.append(entry)
            continue
        f_half_point = stats.half_kelly_clamped(use_lower_bound=False)
        f_half_shrunk = stats.half_kelly_clamped(use_lower_bound=True)
        entry.update(
            win_rate=round(stats.win_rate, 4),
            payoff_ratio=round(stats.payoff_ratio, 4),
            n_trades=stats.n_trades,
            f_half_point=round(f_half_point, 6),
            f_half_shrunk=round(f_half_shrunk, 6),
        )
        if stats.profit_total_pct is not None:
            entry["profit_total_pct"] = round(stats.profit_total_pct, 2)
        if stats.backtest_start:
            entry["backtest_start"] = stats.backtest_start
        if stats.backtest_end:
            entry["backtest_end"] = stats.backtest_end
        if stats.n_trades < MIN_TRADES_FOR_KELLY:
            entry["status"] = "insufficient_n"
            entry["verdict"] = f"n={stats.n_trades} below {MIN_TRADES_FOR_KELLY} → fallback"
        elif f_half_shrunk == 0:
            entry["status"] = "negative_edge"
            entry["verdict"] = (
                f"negative edge after Wilson shrinkage "
                f"(point f½={f_half_point * 100:.2f}%)"
            )
        else:
            entry["status"] = "ok"
            entry["verdict"] = (
                f"size {f_half_shrunk * 100:.2f}% per trade "
                f"(point f½ {f_half_point * 100:.2f}%)"
            )
        strategies.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_trades_for_kelly": MIN_TRADES_FOR_KELLY,
        "wilson_z": WILSON_Z,
        "strategies": strategies,
    }


def _format_kelly_entry(e: dict) -> str:
    name = e["name"]
    status = e.get("status")
    if status == "no_data":
        return f"  {name}: _no recent backtest_"
    if status == "insufficient_n":
        return f"  {name}: n={e['n_trades']} — _below {e.get('_min_trades', '?')}, fallback_"
    if status == "negative_edge":
        return (
            f"  {name}: ⛔ negative edge after shrinkage "
            f"(point f½={e['f_half_point'] * 100:.2f}% → 0 after Wilson; "
            f"p={e['win_rate']:.2f} b={e['payoff_ratio']:.2f} n={e['n_trades']})"
        )
    if status == "ok":
        return (
            f"  {name}: ✅ {e['f_half_shrunk'] * 100:.2f}% per trade "
            f"(point f½ would be {e['f_half_point'] * 100:.2f}%; "
            f"p={e['win_rate']:.2f} b={e['payoff_ratio']:.2f} n={e['n_trades']})"
        )
    return f"  {name}: {e.get('verdict', '?')}"


def format_kelly_report() -> str:
    """Return a Markdown block summarising Kelly stats for tracked strategies.

    Empty string if no strategies have a recent backtest — keeps the daily
    report short when there's nothing useful to say.
    """
    payload = kelly_status_dict()
    strategies = payload.get("strategies", [])
    if not strategies:
        return ""
    min_n = payload.get("min_trades_for_kelly")
    rows = []
    for e in strategies:
        if "_min_trades" not in e and min_n is not None:
            e["_min_trades"] = min_n
        rows.append(_format_kelly_entry(e))
    return "\n*Kelly Sizing:*\n" + "\n".join(rows)


def write_kelly_status_json(target: Path) -> Path:
    """Compute Kelly status and write it as JSON to ``target``.

    Used by the daily report path so external consumers (dashboard, monitoring,
    jq pipelines) get a fresh snapshot once a day without having to invoke
    the Python directly.
    """
    payload = kelly_status_dict()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2))
    return target


# --------------------------------------------------------------------------
# Helper: house strategy record (quant.strategy_record, migration 032)
# --------------------------------------------------------------------------
# The public track record of the house trend rule (趋势突破策略, Donchian 1h 168/72 on
# BTC/ETH/SOL). quant.strategy_record is the single source of truth for its stats; this
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
# Alert 4: Daily Report
# --------------------------------------------------------------------------
def send_daily_report():
    """
    Send daily summary: portfolio status, sentiment, KOL activity.
    Call once per day (e.g., via --daily flag or at 00:00 UTC).
    """
    state = load_state()
    last_report = state.get("last_daily_report", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if last_report == today:
        logger.info("Daily report already sent today")
        return

    # Gather sentiment data
    sentiment_file = PROJECT_DIR / "sentiment_data" / "latest_sentiment.json"
    try:
        with open(sentiment_file) as f:
            s = json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        s = {}

    fng = s.get("fng_value", "?")
    fng_class = s.get("fng_classification", "?")
    score = s.get("combined_score", 0)
    kol = s.get("kol_score", 0)
    kol_n = s.get("kol_mentions", 0)
    btc = s.get("btc_price", 0)

    # Get Supabase history
    history_str = ""
    try:
        import os
        su = os.environ.get("SUPABASE_URL", "")
        sk = os.environ.get("SUPABASE_KEY", "")
        if su and sk:
            resp = requests.get(
                f"{su}/rest/v1/sentiment_snapshots",
                headers={"apikey": sk, "Authorization": f"Bearer {sk}"},
                params={"select": "combined_score,signal", "order": "timestamp.desc", "limit": "6"},
                timeout=10,
            )
            if resp.status_code == 200:
                hist = resp.json()
                trend = " → ".join(f"{h['combined_score']:+.2f}" for h in reversed(hist))
                history_str = f"\nTrend (24h): {trend}"
    except Exception:
        pass

    # House strategy record (quant.strategy_record, migration 032) — replaces the old
    # quant.nautilus_trades P&L, which node restarts made misleading (stale "open" rows per
    # position). Graceful no-op when TIMESCALE_URL isn't provided to this service.
    timescale_url = os.environ.get("TIMESCALE_URL", "")
    strategy = strategy_record_block(timescale_url)

    # Growth funnel from first-party analytics (quant.web_events, migration 020) —
    # the validation plan's daily eyes: visitors / signups / activation / D1 return.
    growth = ""
    if psycopg2 is not None and timescale_url:
        try:
            conn = psycopg2.connect(timescale_url)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        WITH yest AS (
                          SELECT * FROM quant.web_events
                          WHERE ts >= now() - interval '24 hours'
                        )
                        SELECT
                          (SELECT count(DISTINCT visitor) FROM yest WHERE event = 'page_view'),
                          (SELECT count(*) FROM yest WHERE event = 'page_view'),
                          (SELECT count(*) FROM yest WHERE event = 'signup'),
                          (SELECT count(*) FROM yest WHERE event = 'backtest_submit'),
                          (SELECT count(*) FROM yest WHERE event = 'signal_create'),
                          (SELECT count(*) FROM yest WHERE event = 'telegram_bound'),
                          -- D1 return: visitors seen yesterday AND in the 24h before
                          (SELECT count(DISTINCT y.visitor) FROM yest y
                            WHERE EXISTS (SELECT 1 FROM quant.web_events p
                                           WHERE p.visitor = y.visitor
                                             AND p.ts >= now() - interval '48 hours'
                                             AND p.ts <  now() - interval '24 hours'))
                    """)
                    vis, pv, su_n, bt, sig, tg, ret = cur.fetchone()
            finally:
                conn.close()
            if (vis or 0) > 0:
                growth = (
                    f"\n*Growth (24h):*\n"
                    f"  Visitors: {vis}  |  Views: {pv}  |  D1 return: {ret}\n"
                    f"  Signups: {su_n}  |  Backtests: {bt}  |  Signals: {sig}  |  TG bound: {tg}"
                )
        except Exception as e:
            logger.warning(f"growth query failed: {e}")

    # Top headlines from the news ingest (quant.news_items) — macro/official
    # sources (Fed/SEC/ECB) first, then the freshest of the last 24h.
    news = ""
    if psycopg2 is not None and timescale_url:
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
            if rows:
                lines = "\n".join(
                    f"  • [{src}] {(title or '')[:80]}" for src, title in rows
                )
                news = f"\n*Market wire (24h):*\n{lines}"
        except Exception as e:
            logger.warning(f"news query failed: {e}")

    # Build the message line-by-line. Previous version chained f-strings inside
    # parentheses with a `... if btc else ""` ternary on one of them — that
    # binds the conditional at the PYTHON expression level (not string level),
    # which silently collapsed the *entire* message to "" whenever btc was 0.
    parts = [
        f"*Daily Report* 📊 {today}",
        "─" * 30,
        "*Market:*",
    ]
    if btc:
        parts.append(f"  BTC: ${btc:,.0f}")
    parts.extend([
        f"  Fear & Greed: {fng} ({fng_class})",
        f"  Sentiment: {score:+.2f}",
        f"  KOL Activity: {kol:+.2f} ({kol_n} mentions)",
    ])
    message = "\n".join(parts) + history_str + strategy + growth + news + format_kelly_report()

    # Snapshot the structured Kelly status alongside the Telegram send so
    # dashboards / monitoring can read the same numbers without re-running
    # this script.
    #
    # We write to two locations:
    #   - `sentiment_data/kelly_status.json` — local copy for jq / monitoring
    #     pipelines that already look in sentiment_data/ for daily artifacts.
    #   - `web/apps/app/static/kelly_status.json` — the path the dashboard
    #     fetches. A subsequent `wrangler deploy` is still required to push
    #     this to Cloudflare, but writing it here means the static asset on
    #     disk always reflects the most recent backtest data so the next
    #     deploy carries fresh numbers automatically.
    for path in (
        PROJECT_DIR / "sentiment_data" / "kelly_status.json",
        PROJECT_DIR / "web" / "apps" / "app" / "static" / "kelly_status.json",
    ):
        try:
            if path.parent.exists():
                write_kelly_status_json(path)
        except Exception as e:
            logger.warning(f"Kelly status write to {path} failed: {e}")

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
    parser.add_argument("--sentiment", action="store_true", help="Check sentiment shift only")
    parser.add_argument("--daily", action="store_true", help="Send daily report")
    parser.add_argument("--kelly", action="store_true",
                        help="Print Kelly verdict per strategy (does not send Telegram)")
    parser.add_argument("--json", action="store_true",
                        help="With --kelly, emit machine-readable JSON instead of Markdown")
    parser.add_argument("--write-kelly-status",
                        metavar="PATH",
                        help="Compute Kelly status and write JSON to PATH, then exit")
    parser.add_argument("--all", action="store_true", help="Run all checks (default)")
    args = parser.parse_args()

    if args.write_kelly_status:
        out = write_kelly_status_json(Path(args.write_kelly_status))
        print(f"wrote {out}")
        sys.exit(0)

    if args.kelly:
        if args.json:
            print(json.dumps(kelly_status_dict(), indent=2))
        else:
            print(format_kelly_report() or "(no Kelly data)")
        sys.exit(0)

    run_all = args.all or not (args.kol or args.sentiment or args.daily)

    if args.kol or run_all:
        n = check_kol_alerts()
        print(f"KOL alerts: {n} new")

    if args.sentiment or run_all:
        check_sentiment_shift()
        print("Sentiment shift: checked")

    if args.daily:
        send_daily_report()
        print("Daily report: sent")
