"""User-facing Telegram alert dispatcher — the retention loop behind /start 订阅.

Two jobs, one loop:
  1. BIND: long-poll Telegram getUpdates for "/start <token>"; match the token to
     quant.telegram_links.link_token and bind that chat_id (web UI shows 已绑定).
     This process is the ONLY getUpdates consumer for @freemanXbtc_bot (the other
     services send only) — do not add a second poller.
  2. FAN OUT: watch for new events and push them to subscribed chats:
       'strategy_signals' — the house trend rule's buy/sell calls on BTC/ETH/SOL
                            (quant.strategy_signals, written by signal_evaluator.py)
                            + a Monday (UTC) scorecard from quant.strategy_record;
                            exits and the scorecard go out as share-card images
                            (share_card.py), falling back to text
       'dca_boost'        — smart-DCA "定投加倍日" from quant.dca_boost_days, at most once
                            per 7 days unless the multiple goes up
       'equity_trades'    — quant.nautilus_trades asset_class='equity' opens/closes
     plus per-user pushes (fires of the user's own signals, monthly DCA-plan reminder).

Messages are plain-Chinese (glossary tone from /start), always carry a
"不构成投资建议" line, and link back to the dashboard. Tool, not advice. House
strategy messages are "规则模拟信号": returns are net of 0.1% fee per side, the stats
come only from quant.strategy_record, and backfilled history (live=false) is labelled
回溯计算 and never pushed as a call.

State (telegram offset, equity watermark, once-per-period gates) lives in
~/.config/quant/alert-dispatcher.json so restarts neither replay nor skip. Strategy
signals need no watermark: entry_notified_at / exit_notified_at mark delivery.

Env (via sops exec-env secrets.env + EnvironmentFile, mirroring quant-alerts):
  TELEGRAM_BOT_TOKEN   bot token (sops)
  TIMESCALE_URL        postgres DSN for the quant role
  DISPATCH_INTERVAL    seconds between fan-out scans (default 60)

Run: .venv-bots/bin/python strategies/alert_dispatcher.py
All errors are logged and swallowed — an outage must never crash the loop.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests

from strategy_record import STRATEGY

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DSN = os.environ.get("TIMESCALE_URL", "")
INTERVAL = int(os.environ.get("DISPATCH_INTERVAL", "60"))
STATE_PATH = Path.home() / ".config" / "quant" / "alert-dispatcher.json"
DASH = "https://starslab.qzz.io"
RECORD_URL = f"{DASH}/record"

TOPIC_ZH = {
    "strategy_signals": "策略买卖信号 + 每周战绩",
    "dca_boost": "定投加倍日提醒",
    "equity_trades": "美股模拟盘交易",
}

DISCLAIMER = "\n\n⚠️ 自动信号,不构成投资建议。"
SIM_DISCLAIMER = "\n\n⚠️ 规则模拟信号,不构成投资建议。"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"tg_offset": 0, "last_eq_synced": None}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))


def tg(method: str, **params):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=params, timeout=35)
    except requests.RequestException as e:
        # requests puts the full URL (bot token included) in its message — never log it.
        raise RuntimeError(f"telegram {method}: {str(e).replace(TOKEN, '<token>')}") from None
    d = r.json()
    if not d.get("ok"):
        raise RuntimeError(f"telegram {method}: {d.get('description')}")
    return d["result"]


def send(chat_id: int, text: str) -> bool:
    try:
        tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
           disable_web_page_preview=True)
        return True
    except Exception as e:
        log(f"send to {chat_id} failed: {e!r}")
        return False


def send_photo(chat_id: int, photo: bytes | str, caption: str) -> str | None:
    """photo = PNG bytes (first chat) or the file_id Telegram returned for it (the rest —
    uploaded once, reused). Returns the file_id, or None on failure."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    try:
        if isinstance(photo, bytes):
            r = requests.post(url, data=data, timeout=60,
                              files={"photo": ("card.png", photo, "image/png")})
        else:
            r = requests.post(url, data={**data, "photo": photo}, timeout=35)
        d = r.json()
        if not d.get("ok"):
            raise RuntimeError(d.get("description"))
        return d["result"]["photo"][-1]["file_id"]
    except Exception as e:
        # requests puts the full URL (bot token included) in its message — never log it.
        log(f"send photo to {chat_id} failed: {str(e).replace(TOKEN, '<token>')}")
        return None


def render_card(fn: str, *args) -> bytes | None:
    """A share card, or None (Pillow/font missing, render bug) — callers fall back to text."""
    try:
        import share_card
        return getattr(share_card, fn)(*args)
    except Exception as e:
        log(f"share card {fn} failed (sending text): {e!r}")
        return None


def broadcast(chats: list[int], text: str, card: bytes | None = None,
              caption: str | None = None) -> int:
    """Send `text` to every chat — as the caption of `card` when there is one (or `caption`
    on the photo followed by `text` as a message, for texts over Telegram's caption limit).
    A chat whose photo fails still gets the text. Returns how many chats got the text."""
    delivered = 0
    photo: bytes | str | None = card
    for chat in chats:
        ok = False
        if photo is not None:
            fid = send_photo(chat, photo, caption or text)
            if fid:
                photo = fid
                ok = True if caption is None else send(chat, text)
        delivered += ok or send(chat, text)
    return delivered


def db():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    return conn


# ---------- job 1: bind /start tokens ----------

def poll_bindings(conn, state: dict) -> None:
    """Short getUpdates poll; bind '/start <token>' messages to telegram_links rows."""
    try:
        updates = tg("getUpdates", offset=state["tg_offset"] + 1, timeout=20,
                     allowed_updates=["message"])
    except Exception as e:
        log(f"getUpdates failed: {e!r}")
        return
    for u in updates:
        state["tg_offset"] = max(state["tg_offset"], u["update_id"])
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat_id = (msg.get("chat") or {}).get("id")
        if not chat_id or not text.startswith("/start"):
            continue
        parts = text.split(maxsplit=1)
        token = parts[1].strip() if len(parts) > 1 else ""
        if not token:
            send(chat_id, "你好!请从 starslab.qzz.io 的订阅页面点「绑定 Telegram」进入,"
                          "这样我才知道你是谁。")
            continue
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE quant.telegram_links
                          SET chat_id = %s, bound_at = now()
                        WHERE link_token = %s
                        RETURNING user_id, topics""",
                    (chat_id, token),
                )
                row = cur.fetchone()
        except Exception as e:
            log(f"bind update failed: {e!r}")
            continue
        if row:
            topics = row[1] or []
            topic_zh = "、".join(TOPIC_ZH.get(t, t) for t in topics) or "(暂未选择)"
            send(chat_id,
                 f"✅ 绑定成功!已订阅:{topic_zh}\n\n"
                 f"信号触发时会在这里通知你。策略规则与全部历史战绩:{RECORD_URL}"
                 f"{DISCLAIMER}")
            log(f"bound chat {chat_id} to user {row[0]}")
        else:
            send(chat_id, "这个绑定链接无效或已过期,请回到网站重新点「绑定 Telegram」。")


# ---------- job 2: fan out new events ----------

def subscribers(conn, topic: str) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chat_id FROM quant.telegram_links WHERE chat_id IS NOT NULL AND %s = ANY(topics)",
            (topic,),
        )
        return [r[0] for r in cur.fetchall()]


# ---------- house strategy: 趋势突破策略 (migration 032) ----------
#
# Formatters are pure (row dicts in → HTML text out) so they're unit-testable without a
# DB or Telegram. Every stat comes from quant.strategy_record / strategy_trades; the only
# math done here is the cross-asset roll-up in portfolio(). Bar timestamps are Binance
# close times (hh:59:59.999) and are shown as the round hour they close at, in UTC.

def _utc(ts: datetime) -> datetime:
    return (ts + timedelta(milliseconds=1)).astimezone(timezone.utc)


def _md(ts: datetime) -> str:
    d = _utc(ts)
    return f"{d.month}/{d.day}"


def _when(ts: datetime) -> str:
    return f"{_md(ts)} {_utc(ts):%H:%M} UTC"


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _days(d) -> str:
    return f"{float(d):g}"


def portfolio(record: list[dict]) -> dict:
    """Cross-asset roll-up of quant.strategy_record rows — the only stats math consumers do:
    equal-weight averages (1/N per asset, no rebalancing), pooled win rate, best trade."""
    priced = [r for r in record if r["sleeve_ret"] is not None and r["hold_ret"] is not None]
    n_closed = sum(r["n_closed"] for r in record)
    n_wins = sum(r["n_wins"] for r in record)
    best = max((r for r in record if r["best_ret"] is not None),
               key=lambda r: r["best_ret"], default=None)
    return {
        "ret": sum(r["sleeve_ret"] for r in priced) / len(priced) if priced else None,
        "hold_ret": sum(r["hold_ret"] for r in priced) / len(priced) if priced else None,
        "n_closed": n_closed,
        "n_wins": n_wins,
        "win_rate": n_wins / n_closed if n_closed else None,
        "best_ret": best["best_ret"] if best else None,
        "best_asset": best["asset"] if best else None,
        "start_ts": min((r["start_ts"] for r in record if r["start_ts"]), default=None),
        "last_ts": max((r["last_ts"] for r in record if r["last_ts"]), default=None),
    }


def _since(start_ts: datetime | None, now: datetime) -> str:
    if start_ts is None:
        return "记录中"
    s = _utc(start_ts)
    if s.year == now.year and (s.month, s.day) == (1, 1):
        return "今年"
    return f"{s:%Y-%m-%d} 以来"


def _hint(record: list[dict], now: datetime) -> str | None:
    """The honest expectation line: most trend trades lose; a few big trends pay."""
    p = portfolio(record)
    if not p["n_closed"]:
        return None
    best = f"{_since(p['start_ts'], now)}最大一笔 {p['best_asset']} {_pct(p['best_ret'])}"
    loss_share = 1 - p["win_rate"]
    if loss_share >= 0.5:
        return f"提示:趋势信号约 {round(loss_share * 10)} 成会亏损离场,赚钱靠少数大行情({best})。"
    return f"提示:历史上约 {round(p['win_rate'] * 10)} 成信号盈利离场({best})。"


def format_entry(t: dict, record: list[dict], now: datetime) -> str:
    """Entry card for one quant.strategy_trades row."""
    lines = [
        f"🟢 <b>策略信号 · {t['asset']} 突破买入</b>",
        f"1 小时收盘 {_money(t['entry_price'])}({_when(t['entry_ts'])}),"
        f"突破过去 7 天最高点 {_money(t['entry_level'])}",
    ]
    exit_rule = "离场规则:1 小时收盘跌破过去 3 天最低点"
    rec = next((r for r in record if r["asset"] == t["asset"]), None)
    # The current exit line only means something while this trade is still open.
    if t["exit_ts"] is None and rec and rec["channel_low"] is not None and rec["last_close"]:
        dist = rec["channel_low"] / rec["last_close"] - 1
        exit_rule += f"(当前 {_money(rec['channel_low'])},距现价 {_pct(dist)})"
    lines.append(exit_rule)
    hint = _hint(record, now)
    if hint:
        lines.append(hint)
    lines.append(f"👉 全部信号与实时持仓:{RECORD_URL}")
    return "\n".join(lines) + SIM_DISCLAIMER


def format_exit(t: dict) -> str:
    """Exit card for one closed quant.strategy_trades row (net_ret already net of fees)."""
    lines = [
        f"🔴 <b>策略信号 · {t['asset']} 跌破离场</b>",
        f"1 小时收盘 {_money(t['exit_price'])}({_when(t['exit_ts'])}),"
        f"跌破过去 3 天最低点 {_money(t['exit_level'])}",
        f"本次 {_md(t['entry_ts'])} {_money(t['entry_price'])} → "
        f"{_md(t['exit_ts'])} {_money(t['exit_price'])},{_pct(t['net_ret'])}(已扣手续费),"
        f"持有 {_days(t['hold_days'])} 天",
    ]
    if not t["live"]:
        lines.append("(这笔的买入在服务上线前,是按规则回溯计算的,当时没有推送)")
    lines.append(f"👉 全部信号与实时持仓:{RECORD_URL}")
    return "\n".join(lines) + SIM_DISCLAIMER


def format_weekly_scorecard(record: list[dict], recent: list[dict],
                            backfilled_at: datetime | None) -> str:
    """Monday scorecard: open positions, flat assets, last-7-day closes, since-start totals.
    recent = strategy_trades rows closed in the last 7 days; backfilled_at = when the
    pre-launch history was computed (None if there is none)."""
    p = portfolio(record)
    lines = ["📊 <b>趋势突破策略 · 每周战绩</b>"]
    if p["last_ts"]:
        lines.append(f"数据截至 {_when(p['last_ts'])}")

    held = [r for r in record if r["open_entry_ts"] is not None]
    if held:
        lines.append("\n<b>当前持有</b>")
        for r in held:
            tag = "" if r["open_live"] else "(回溯计算)"
            lines.append(f"{r['asset']}:{_md(r['open_entry_ts'])} {_money(r['open_entry_price'])} 买入"
                         f" → 现价 {_money(r['last_close'])},浮动 {_pct(r['open_ret'])}{tag}")
            if r["channel_low"] is not None:
                dist = r["channel_low"] / r["last_close"] - 1
                lines.append(f"  离场线 {_money(r['channel_low'])}(距现价 {_pct(dist)})")

    flat = [r for r in record if r["open_entry_ts"] is None]
    if flat:
        lines.append("\n<b>空仓等待</b>")
        for r in flat:
            if r["channel_high"] is not None:
                dist = r["channel_high"] / r["last_close"] - 1
                lines.append(f"{r['asset']}:现价 {_money(r['last_close'])},1 小时收盘突破 "
                             f"{_money(r['channel_high'])}(距现价 {_pct(dist)})触发买入信号")
            else:
                lines.append(f"{r['asset']}:空仓")

    lines.append("\n<b>近 7 天平仓</b>")
    for t in recent:
        tag = "" if t["live"] else "(回溯计算)"
        lines.append(f"{t['asset']}:{_md(t['entry_ts'])} → {_md(t['exit_ts'])},"
                     f"{_pct(t['net_ret'])}{tag}")
    if not recent:
        lines.append("无")

    start = f"{_utc(p['start_ts']):%Y-%m-%d}" if p["start_ts"] else "开始记录"
    lines.append(f"\n<b>{start} 至今</b>")
    if p["ret"] is not None:
        assets = "/".join(r["asset"] for r in record)
        lines.append(f"$1,000 平均分给 {assets} 跟随全部信号 → "
                     f"${1000 * (1 + p['ret']):,.0f}({_pct(p['ret'])})")
        lines.append(f"同期买入持有 → ${1000 * (1 + p['hold_ret']):,.0f}({_pct(p['hold_ret'])})")
    if p["n_closed"]:
        lines.append(f"已平仓 {p['n_closed']} 笔,胜率 {p['win_rate'] * 100:.0f}%,"
                     f"最大一笔 {p['best_asset']} {_pct(p['best_ret'])}")
    else:
        lines.append("暂无已平仓交易")
    note = "收益已扣买卖各 0.1% 手续费"
    if backfilled_at:
        note += f";{_md(backfilled_at)} 服务上线前的记录是按规则回溯计算的,不是当时的实时推送"
    lines.append(note + "。")
    lines.append(f"\n👉 全部信号与实时持仓:{RECORD_URL}")
    return "\n".join(lines) + SIM_DISCLAIMER


def load_record(conn) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM quant.strategy_record WHERE strategy = %s ORDER BY asset",
                    (STRATEGY,))
        return cur.fetchall()


def pending_strategy_trades(conn) -> list[dict]:
    """Trades with an undelivered leg. Entries: live only (backfill is pre-notified anyway).
    Exits: any row — a position opened in the backfilled history but closed after launch
    is a real-time exit (format_exit labels its entry as 回溯)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT * FROM quant.strategy_trades
                WHERE strategy = %s
                  AND ((live AND entry_notified_at IS NULL)
                       OR (exit_ts IS NOT NULL AND exit_notified_at IS NULL))
                ORDER BY coalesce(exit_ts, entry_ts)""",
            (STRATEGY,),
        )
        return cur.fetchall()


def mark_notified(conn, trade_id: int, leg: str) -> None:
    col = {"entry": "entry_notified_at", "exit": "exit_notified_at"}[leg]
    with conn.cursor() as cur:
        cur.execute(f"UPDATE quant.strategy_signals SET {col} = now() WHERE id = %s", (trade_id,))


def fan_out_strategy_signals(conn, now: datetime | None = None) -> None:
    """Push pending house-strategy entries/exits to 'strategy_signals' subscribers, oldest
    first (a row with both legs pending: entry, then exit). Each leg is marked notified right
    after its send — restart-safe, no double send — and ALSO with zero subscribers, so a
    later first subscriber isn't flooded with a backlog. A leg that reached no subscriber at
    all (Telegram down) stays pending, and so does every later leg: the next tick retries
    them in order. One chat that blocked the bot doesn't hold up the others."""
    rows = pending_strategy_trades(conn)
    if not rows:
        return
    now = now or datetime.now(timezone.utc)
    record = load_record(conn)
    chats = subscribers(conn, "strategy_signals")
    legs = []
    for t in rows:
        if t["live"] and t["entry_notified_at"] is None:
            legs.append((t["entry_ts"], 0, "entry", t))
        if t["exit_ts"] is not None and t["exit_notified_at"] is None:
            legs.append((t["exit_ts"], 1, "exit", t))
    legs.sort(key=lambda x: (x[0], x[1]))
    log(f"strategy fan-out: {len(legs)} signal(s) -> {len(chats)} subscriber(s)")
    for _ts, _order, leg, t in legs:
        if leg == "entry":
            delivered = broadcast(chats, format_entry(t, record, now))
        else:
            card = render_card("render_exit_card", t, record) if chats else None
            delivered = broadcast(chats, format_exit(t), card)
        if chats and not delivered:
            log(f"strategy {leg} {t['asset']} (trade {t['id']}): 0/{len(chats)} delivered, "
                "left pending for the next tick")
            return
        mark_notified(conn, t["id"], leg)
        log(f"strategy {leg} {t['asset']} (trade {t['id']}) -> {delivered}/{len(chats)} chat(s), "
            "marked notified")


def recent_closed(conn, since: datetime) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT asset, entry_ts, exit_ts, net_ret, live FROM quant.strategy_trades
                WHERE strategy = %s AND exit_ts >= %s ORDER BY exit_ts""",
            (STRATEGY, since),
        )
        return cur.fetchall()


def backfilled_at(conn) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(created_at) FROM quant.strategy_signals "
                    "WHERE strategy = %s AND NOT live", (STRATEGY,))
        return cur.fetchone()[0]


def fan_out_weekly_scorecard(conn, state: dict, now: datetime | None = None) -> None:
    """Monday (UTC) scorecard to 'strategy_signals' subscribers, once per ISO week
    (state['last_scorecard_week']). Nothing is sent — and the week stays open — while
    quant.strategy_record is empty, and the week also stays open (retried next tick) when
    no subscriber could be reached."""
    now = now or datetime.now(timezone.utc)
    if now.weekday() != 0:
        return
    iso = now.isocalendar()
    week = f"{iso[0]}-W{iso[1]:02d}"
    if state.get("last_scorecard_week") == week:
        return
    record = load_record(conn)
    if not record:
        return
    text = format_weekly_scorecard(record, recent_closed(conn, now - timedelta(days=7)),
                                   backfilled_at(conn))
    chats = subscribers(conn, "strategy_signals")
    card = render_card("render_scorecard", record, now) if chats else None
    delivered = broadcast(chats, text, card, caption="📊 <b>趋势突破策略 · 每周战绩</b>(明细见下条)")
    if chats and not delivered:
        log(f"weekly scorecard {week}: 0/{len(chats)} delivered, retrying next tick")
        return
    state["last_scorecard_week"] = week
    log(f"weekly scorecard {week} -> {delivered}/{len(chats)} subscriber(s)")


# ---------- smart-DCA boost days ----------

def boost_push_due(row: dict, last_pushed: dict | None) -> bool:
    """Push a boosted day unless one went out in the last 7 days at the same or a higher
    multiple — FNG hovers around 25, so boosts flicker on and off day to day."""
    if row["units"] <= 1:
        return False
    if last_pushed is None:
        return True
    return (row["day"] - last_pushed["day"]).days >= 7 or row["units"] > last_pushed["units"]


def format_dca_boost(row: dict) -> str:
    parts = ["基础 1 份"]
    if row["fear_add"]:
        parts.append(f"{'极度恐慌' if row['fng'] <= 15 else '恐慌'}加 {row['fear_add']:g} 份")
    if row["dip_add"]:
        parts.append(f"大跌加 {row['dip_add']:g} 份")
    lines = [f"🟢 <b>今天是定投加倍日 · BTC</b>"]
    mood = "极度恐慌" if row["fng"] <= 15 else "恐慌" if row["fng"] <= 25 else "中性"
    lines.append(f"恐惧贪婪指数 {row['fng']}({mood})")
    if row["drawdown"] is not None:
        lines.append(f"BTC {_money(row['btc_close'])},距 30 天高点 {_money(row['high_30d'])} "
                     f"{_pct(row['drawdown'])}")
    lines.append(f"按规则,今天这笔定投 ×{row['units']:g}({' + '.join(parts)})")
    lines.append("规则:恐惧贪婪 ≤25 加 3 份、≤15 加 5 份;比 30 天高点低 20% 以上再加 2 份。"
                 "恐慌可能持续很久,加倍不代表马上反弹。")
    if row["ytd_smart_cost"] and row["ytd_plain_cost"]:
        diff = row["ytd_smart_cost"] / row["ytd_plain_cost"] - 1
        lines.append(f"2026 年至今按这条规则每天定投,平均成本 ${row['ytd_smart_cost']:,.0f},"
                     f"比每天固定金额定投(${row['ytd_plain_cost']:,.0f}){'低' if diff < 0 else '高'} "
                     f"{abs(diff) * 100:.1f}%;{row['ytd_days']} 天里有 {row['ytd_boosted_days']} 天是加倍日。")
    lines.append(f"👉 记一笔、看你的真实均价:{DASH}/dca")
    return "\n".join(lines) + SIM_DISCLAIMER


def fan_out_dca_boost(conn, now: datetime | None = None) -> None:
    """Push due boost days to 'dca_boost' subscribers. Every processed row gets notified_at
    (pushed = whether a message went out); a row that reached no subscriber at all stays
    pending for the next tick. Rows older than yesterday are never pushed ("今天" would lie)."""
    now = now or datetime.now(timezone.utc)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM quant.dca_boost_days WHERE notified_at IS NULL ORDER BY day")
        rows = cur.fetchall()
        if not rows:
            return
        cur.execute("SELECT * FROM quant.dca_boost_days WHERE pushed ORDER BY day DESC LIMIT 1")
        last_pushed = cur.fetchone()
    chats = subscribers(conn, "dca_boost")
    for row in rows:
        due = boost_push_due(row, last_pushed) and (now.date() - row["day"]).days <= 1
        if due:
            delivered = broadcast(chats, format_dca_boost(row))
            if chats and not delivered:
                log(f"dca boost {row['day']}: 0/{len(chats)} delivered, retrying next tick")
                return
            last_pushed = row
            log(f"dca boost {row['day']} ×{row['units']:g} -> {delivered}/{len(chats)} chat(s)")
        with conn.cursor() as cur:
            cur.execute("UPDATE quant.dca_boost_days SET notified_at = now(), pushed = %s "
                        "WHERE day = %s", (due, row["day"]))


def fan_out_equity(conn, state: dict) -> None:
    last = state.get("last_eq_synced")
    with conn.cursor() as cur:
        if last:
            # 'superseded' = TradeLedger closing a stale incarnation after a node restart:
            # bookkeeping, not a trade — no fill, no close price, nothing to announce. The
            # incarnation that replaced it (open_date = the superseded row's close_date) is the
            # same holding re-opened by the restart, so its "open" isn't announced either.
            cur.execute(
                "SELECT instrument, is_short, open_date, close_date, open_rate, close_rate, "
                "profit_pct, synced_at FROM quant.nautilus_trades t "
                "WHERE asset_class='equity' AND synced_at > %s "
                "AND exit_reason IS DISTINCT FROM 'superseded' "
                "AND NOT (close_date IS NULL AND EXISTS ("
                "  SELECT 1 FROM quant.nautilus_trades p "
                "   WHERE p.trader_id = t.trader_id AND p.position_id = t.position_id "
                "     AND p.exit_reason = 'superseded' AND p.close_date = t.open_date)) "
                "ORDER BY synced_at", (last,))
        else:
            cur.execute("SELECT max(synced_at) FROM quant.nautilus_trades WHERE asset_class='equity'")
            mx = cur.fetchone()[0]
            state["last_eq_synced"] = mx.isoformat() if mx else datetime.now(timezone.utc).isoformat()
            return
        rows = cur.fetchall()
    if not rows:
        return
    chats = subscribers(conn, "equity_trades")
    log(f"equity fan-out: {len(rows)} trade event(s) -> {len(chats)} subscriber(s)")
    for inst, is_short, od, cd, orate, crate, ppct, synced in rows:
        side = "做空" if is_short else "做多"
        if cd:  # closed round-trip
            ret = f"{ppct * 100:+.2f}%" if ppct is not None else "—"
            text = (f"📈 <b>美股模拟盘平仓:{inst}</b>\n"
                    f"{side} {orate} → {crate},收益 {ret}\n"
                    f"完整记录:{DASH}/nautilus")
        else:
            text = (f"📈 <b>美股模拟盘开仓:{inst}</b>\n"
                    f"{side} @ {orate}(IB 模拟盘,真实信号)\n"
                    f"实时持仓:{DASH}/nautilus")
        text += DISCLAIMER
        for chat in chats:
            send(chat, text)
        state["last_eq_synced"] = synced.isoformat()


def fan_out_plan_reminders(conn, state: dict) -> None:
    """Monthly DCA-plan reminder — the discipline-coach nudge. On the 1st of each month
    (UTC; mirrors dcaSim's schedule = monthly budget on the 1st), remind every
    Telegram-bound user who saved a dca_plan: their OWN plan amount, split per their
    OWN mix. Tool framing throughout — we restate their plan, we don't advise.
    Daily-gated via state['last_plan_reminder_date'] so restarts can't double-send."""
    today = datetime.now(timezone.utc).date()
    if state.get("last_plan_reminder_date") == today.isoformat():
        return
    if today.day != 1:
        state["last_plan_reminder_date"] = today.isoformat()
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.user_id, p.dca_plan, l.chat_id
                     FROM quant.user_preferences p
                     JOIN quant.telegram_links l ON l.user_id = p.user_id
                    WHERE l.chat_id IS NOT NULL AND p.dca_plan IS NOT NULL"""
            )
            rows = cur.fetchall()
    except Exception as e:
        log(f"plan reminder query failed: {e!r}")
        return
    sent = 0
    for user_id, plan, chat_id in rows:
        try:
            monthly = float((plan or {}).get("monthly_usdt") or 0)
            if monthly <= 0:
                continue
            mix = (plan or {}).get("mix") or {}
            parts = [f"{c} ${monthly * float(p) / 100:,.0f}"
                     for c, p in mix.items() if float(p or 0) > 0]
            split = "(" + " · ".join(parts) + ")" if parts else ""
            send(chat_id,
                 f"📅 <b>今天是你的定投日</b>\n"
                 f"按你保存的计划:本月投入 ${monthly:,.0f} {split}\n\n"
                 f"买完回来记一笔,看看你的真实均价:{DASH}/dca\n"
                 f"连跌的时候最难坚持 —— 也最重要。"
                 f"{DISCLAIMER}")
            sent += 1
        except Exception as e:
            log(f"plan reminder for {user_id} failed: {e!r}")
    state["last_plan_reminder_date"] = today.isoformat()
    if sent:
        log(f"plan reminders sent: {sent}")


def fan_out_user_fires(conn) -> None:
    """Push pending quant.signal_fires (user-defined signals from signal_evaluator.py) to
    each fire's OWNER — per-user routing, unlike the broadcast topics above. Wording is
    deliberately "你的信号" — the user's own rule fired; never advice. notified_at marks
    delivery so restarts can't double-send (no watermark needed)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT f.id, f.details, s.name, s.asset, s.timeframe, l.chat_id
                 FROM quant.signal_fires f
                 JOIN quant.user_signals s ON s.id = f.signal_id
                 LEFT JOIN quant.telegram_links l ON l.user_id = f.user_id
                WHERE f.notified_at IS NULL
                ORDER BY f.id
                LIMIT 50"""
        )
        rows = cur.fetchall()
    if not rows:
        return
    log(f"user-signal fan-out: {len(rows)} fire(s)")
    for fid, details, name, asset, tf, chat_id in rows:
        d = details or {}
        ok = True
        if chat_id:  # unbound users still see fires in the web UI; nothing to push
            text = (f"🔔 <b>你的信号「{name}」触发了</b>\n"
                    f"{asset} · {tf}\n{d.get('message', '')}\n\n"
                    f"这是你自己设定的规则提醒。管理信号:{DASH}/backtest"
                    f"{DISCLAIMER}")
            ok = send(chat_id, text)
        if ok:
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE quant.signal_fires SET notified_at=now() WHERE id=%s", (fid,))
            except Exception as e:
                log(f"mark notified {fid} failed: {e!r}")


def main() -> int:
    if not TOKEN or not DSN:
        print("TELEGRAM_BOT_TOKEN / TIMESCALE_URL required", file=sys.stderr)
        return 2
    state = load_state()
    log(f"alert dispatcher up (interval={INTERVAL}s, state={STATE_PATH})")
    conn = None
    last_fan = 0.0
    while True:
        try:
            if conn is None or conn.closed:
                conn = db()
            poll_bindings(conn, state)  # ~20s long-poll = the loop's natural tick
            if time.time() - last_fan >= INTERVAL:
                # One failing stream (e.g. a missing grant) must not starve the others.
                for job, args in ((fan_out_strategy_signals, (conn,)),
                                  (fan_out_weekly_scorecard, (conn, state)),
                                  (fan_out_dca_boost, (conn,)),
                                  (fan_out_equity, (conn, state)),
                                  (fan_out_user_fires, (conn,)),
                                  (fan_out_plan_reminders, (conn, state))):
                    try:
                        job(*args)
                    except Exception as e:
                        log(f"{job.__name__} failed (continuing): {e!r}")
                last_fan = time.time()
            save_state(state)
        except KeyboardInterrupt:
            save_state(state)
            return 0
        except Exception as e:
            log(f"loop error (continuing): {e!r}")
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            conn = None
            time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
