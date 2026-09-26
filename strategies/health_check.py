"""Health check — tells the operator chat when something silently stops.

Runs every 10 min on two hosts that watch each other through quant.health_heartbeats:
  --role server  oracle-arm-002 (nur quant-collectors timer): failed/stopped system units,
                 data freshness of the tables the collectors/evaluator write, the public
                 API + /record page, and the desk heartbeat.
  --role desk    game box (systemd --user timer): failed/stopped user units, a real IB
                 API handshake (an open port is not enough — a stuck Gateway still accepts
                 the TCP connection), and the server heartbeat.

Why: in 2026-09 every one of these failed for a week or more without anyone noticing
(game-box units after a repo move, IB Gateway stuck at a login dialog, a datadog restart
loop, the backtest runner's auth error).

Alert policy: a check must fail ALERT_AFTER consecutive runs before it alerts (network
blips), a recovery is announced once, and a still-failing check is re-announced every
REMIND_HOURS. State lives in a small JSON file so restarts neither re-alert nor forget.

Env: TIMESCALE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (operator chat).
     HEALTH_STATE (optional state-file path), IB_HOST/IB_PORT (desk).
Run: python strategies/health_check.py --role server|desk [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
DSN = os.environ.get("TIMESCALE_URL", "")
STATE_PATH = Path(os.environ.get(
    "HEALTH_STATE", Path.home() / ".config" / "quant" / "health-check.json"))

ALERT_AFTER = 2       # consecutive failing runs before alerting
REMIND_HOURS = 6

# (check id, label, SQL returning one timestamptz, max age in minutes)
SERVER_FRESHNESS = [
    ("fresh:strategy_assets", "策略信号评估(quant-signal-evaluator)",
     "SELECT max(updated_at) FROM quant.strategy_assets", 30),
    ("fresh:news_items", "新闻采集(quant-news-collector)",
     "SELECT max(fetched_at) FROM quant.news_items", 90),
    ("fresh:market_stress", "市场压力指数(quant-stress-index)",
     "SELECT max(ts) FROM quant.market_stress", 180),
    ("fresh:market_snapshots", "行情快照(quant-market-collector)",
     "SELECT max(ts) FROM quant.market_snapshots", 120),
    ("fresh:dca_boost_days", "定投加倍日计算(quant-signal-evaluator)",
     "SELECT max(computed_at) FROM quant.dca_boost_days", 26 * 60),
    ("fresh:account_snapshots", "IB 账户快照(游戏机 quant-account-snapshot)",
     "SELECT max(ts) FROM quant.account_snapshots", 30 * 60),
]

SERVER_URLS = [
    ("url:api", "公开 API", "https://api.panda.qzz.io/strategy_record?limit=1"),
    ("url:record", "网站 /record", "https://starslab.qzz.io/record"),
]

ROLES = {
    "server": {
        "systemctl": ["systemctl"],
        "failed_scope": [],        # a server: any failed system unit matters
        "required": ["postgresql.service", "nautilus-trend.service",
                     "nautilus-accumulator.service", "nautilus-signal.service",
                     "quant-signal-evaluator.service", "quant-alert-dispatcher.service"],
        "peer": ("desk", 120),     # game box may be off for a while — be lenient
    },
    "desk": {
        "systemctl": ["systemctl", "--user"],
        "failed_scope": ["quant-*"],  # a desktop: ignore desktop-session units
        "required": ["quant-equity.service", "quant-dashboard.service",
                     "quant-backtest-runner.service"],
        "peer": ("server", 30),
    },
}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


# ---------- probes: each returns {check_id: (ok, label, detail)} ----------

def probe_units(systemctl: list[str], failed_scope: list[str], required: list[str]) -> dict:
    out: dict = {}
    r = subprocess.run([*systemctl, "list-units", "--failed", "--plain", "--no-legend",
                        *failed_scope],
                       capture_output=True, text=True, timeout=20)
    for line in r.stdout.splitlines():
        unit = line.split()[0] if line.split() else ""
        if unit:
            out[f"unit:{unit}"] = (False, f"服务 {unit}", "failed")
    r = subprocess.run([*systemctl, "is-active", *required],
                       capture_output=True, text=True, timeout=20)
    for unit, state in zip(required, r.stdout.split()):
        cid = f"unit:{unit}"
        if state != "active":
            out[cid] = (False, f"服务 {unit}", state)
        else:
            out.setdefault(cid, (True, f"服务 {unit}", "active"))
    return out


def probe_freshness(conn, now: datetime) -> dict:
    out = {}
    for cid, label, sql, max_min in SERVER_FRESHNESS:
        with conn.cursor() as cur:
            cur.execute(sql)
            ts = cur.fetchone()[0]
        if ts is None:
            out[cid] = (False, label, "表里没有数据")
            continue
        age = (now - ts).total_seconds() / 60
        ok = age <= max_min
        out[cid] = (ok, label, f"{_fmt_age(age)}未更新(上限 {_fmt_age(max_min)})")
    return out


def probe_urls() -> dict:
    out = {}
    for cid, label, url in SERVER_URLS:
        try:
            r = requests.get(url, headers={"Accept": "text/html,application/json"}, timeout=20)
            out[cid] = (r.status_code == 200, label, f"HTTP {r.status_code}")
        except requests.RequestException as e:
            out[cid] = (False, label, type(e).__name__)
    return out


def probe_ib(host: str, port: int) -> dict:
    """TWS API handshake: 'API\\0' + length-prefixed version range; a logged-in Gateway
    answers with its server version. A Gateway stuck at a dialog accepts the TCP
    connection (socat) but never answers — exactly the 2026-09 failure."""
    label = f"IB Gateway API({host}:{port})"
    try:
        with socket.create_connection((host, port), timeout=5) as s:
            s.settimeout(8)
            v = b"v100..187"
            s.sendall(b"API\0" + struct.pack(">I", len(v)) + v)
            ok = bool(s.recv(64))
        return {"ib:api": (ok, label, "握手成功" if ok else "连得上但没有响应(可能卡在登录界面)")}
    except OSError as e:
        return {"ib:api": (False, label, f"连接失败:{type(e).__name__}")}


def heartbeat(conn, role: str, host: str, failing: list[str], peer: tuple[str, int],
              now: datetime, write: bool = True) -> dict:
    peer_role, max_min = peer
    with conn.cursor() as cur:
        if write:
            cur.execute(
                """INSERT INTO quant.health_heartbeats (role, host, ts, failing)
                   VALUES (%s, %s, now(), %s)
                   ON CONFLICT (role) DO UPDATE
                     SET host = EXCLUDED.host, ts = EXCLUDED.ts, failing = EXCLUDED.failing""",
                (role, host, failing))
        cur.execute("SELECT host, ts FROM quant.health_heartbeats WHERE role = %s", (peer_role,))
        row = cur.fetchone()
    label = f"{peer_role} 端健康检查心跳"
    if row is None:
        return {f"peer:{peer_role}": (False, label, "从未上报")}
    age = (now - row[1]).total_seconds() / 60
    return {f"peer:{peer_role}": (age <= max_min, f"{label}({row[0]})",
                                  f"{_fmt_age(age)}未上报(上限 {_fmt_age(max_min)})")}


def _fmt_age(minutes: float) -> str:
    return f"{minutes / 60:.1f} 小时" if minutes >= 120 else f"{minutes:.0f} 分钟"


# ---------- pure alert state machine ----------

def evaluate(state: dict, results: dict, now_ts: float) -> tuple[dict, list[str], list[str]]:
    """(new_state, alert lines, recovery lines). A check absent from `results` counts
    as healthy (e.g. a failed unit that got reset). Callers commit new_state only
    after the message was delivered."""
    checks = {k: dict(v) for k, v in state.get("checks", {}).items()}
    alerts, recovered = [], []
    remind_due = now_ts - state.get("last_remind", 0) >= REMIND_HOURS * 3600

    for cid in sorted(set(checks) | set(results)):
        ok, label, detail = results.get(cid, (True, checks.get(cid, {}).get("label", cid), ""))
        c = checks.get(cid, {"fails": 0, "alerted": False})
        if ok:
            if c.get("alerted"):
                recovered.append(f"✅ {label} 已恢复")
            checks.pop(cid, None)
            continue
        c = {"fails": c["fails"] + 1, "alerted": c.get("alerted", False),
             "label": label, "detail": detail}
        if c["fails"] >= ALERT_AFTER and (not c["alerted"] or remind_due):
            alerts.append(f"🔴 {label}:{detail}" + ("(仍未恢复)" if c["alerted"] else ""))
            c["alerted"] = True
        checks[cid] = c

    new_state = {"checks": checks, "last_remind": state.get("last_remind", 0)}
    if any(checks[c]["alerted"] for c in checks) and remind_due and alerts:
        new_state["last_remind"] = now_ts
    return new_state, alerts, recovered


def format_message(role: str, host: str, alerts: list[str], recovered: list[str]) -> str:
    head = f"🩺 健康检查 · {role}({host})"
    return "\n".join([head, *alerts, *recovered])


# ---------- IO ----------

def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1))


def send(text: str) -> bool:
    if not (TOKEN and CHAT_ID):
        log("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing — not sent")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text,
                                "disable_web_page_preview": True}, timeout=15)
        return r.ok
    except requests.RequestException as e:
        # requests puts the full URL (bot token included) in its message — never log it.
        log(f"telegram send failed: {str(e).replace(TOKEN, '<token>')}")
        return False


def collect(role: str, host: str, write: bool = True) -> dict:
    cfg = ROLES[role]
    now = datetime.now(timezone.utc)
    results: dict = {}
    try:
        results.update(probe_units(cfg["systemctl"], cfg["failed_scope"], cfg["required"]))
    except Exception as e:
        results["probe:units"] = (False, "systemd 查询", repr(e))
    if role == "desk":
        results.update(probe_ib(os.environ.get("IB_HOST", "172.22.240.97"),
                                int(os.environ.get("IB_PORT", "4002"))))
    else:
        results.update(probe_urls())
    try:
        import psycopg2
        conn = psycopg2.connect(DSN, connect_timeout=10)
        conn.autocommit = True
        try:
            if role == "server":
                results.update(probe_freshness(conn, now))
            failing = sorted(k for k, v in results.items() if not v[0])
            results.update(heartbeat(conn, role, host, failing, cfg["peer"], now, write))
        finally:
            conn.close()
        results["db"] = (True, "数据库", "")
    except Exception as e:
        results["db"] = (False, "数据库(TimescaleDB@oracle-arm-002)", f"连不上:{type(e).__name__}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=sorted(ROLES), required=True)
    ap.add_argument("--dry-run", action="store_true", help="print results; send, save and heartbeat nothing")
    args = ap.parse_args()
    host = socket.gethostname()

    results = collect(args.role, host, write=not args.dry_run)
    bad = {k: v for k, v in results.items() if not v[0]}
    log(f"{args.role}@{host}: {len(results)} checks, {len(bad)} failing"
        + (f" — {', '.join(sorted(bad))}" if bad else ""))
    if args.dry_run:
        for k, (ok, label, detail) in sorted(results.items()):
            print(f"  {'ok  ' if ok else 'FAIL'} {k:34} {label} {detail}")
        return 0

    now_ts = datetime.now(timezone.utc).timestamp()
    new_state, alerts, recovered = evaluate(load_state(), results, now_ts)
    if alerts or recovered:
        if not send(format_message(args.role, host, alerts, recovered)):
            return 1  # keep the old state so the next run retries the message
        log(f"sent: {len(alerts)} alert(s), {len(recovered)} recovery(ies)")
    save_state(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
