"""Evaluates user-defined signals (quant.user_signals) on fresh PUBLIC market data and
records fires into quant.signal_fires — the live half of "backtest it, then subscribe to it".

Signal kinds (mirror the backtest playground strategies):
  ema_cross          {ema_fast, ema_slow, direction: 'golden'|'death'|'both'}
  donchian_breakout  {entry_lb, exit_lb, side: 'entry'|'exit'|'both'}
  fng_threshold      {below: int}   — Fear & Greed <= below (evaluated on the daily FNG value)

Data sources (all public, no keys): Binance klines REST for crypto (BTC→BTCUSDT etc.),
Yahoo chart API for equities (NVDA/AMD/QQQ, daily), alternative.me for FNG.

Efficiency: signals are grouped by (kind, asset, timeframe, params-hash) so 100 users on the
same config cost ONE fetch + ONE computation. Fires dedupe per (signal_id, bar_ts) via a
unique index — re-evaluating the same closed bar can't double-notify. Only CLOSED bars are
evaluated (the last, still-forming kline is dropped) so a signal can't flip-flop intrabar.

The alert dispatcher (alert_dispatcher.py) picks up fires with notified_at IS NULL and
pushes them to the owner's bound Telegram chat. Wording stays "你的信号触发了" — the user's
own rule, never advice.

House strategy (the public track record, migration 032): every sweep ALSO runs the house
trend rule (strategy_record.py — Donchian 1h 168/72 long-only on BTC/ETH/SOL, the rule
nautilus_crypto/donchian.py trades) on closed Binance 1h bars, independent of whether any
user signals exist. New entries INSERT quant.strategy_signals (live=true, un-notified — the
dispatcher pushes them to 'strategy_signals' subscribers), exits close the open row, and
quant.strategy_assets keeps last close + the next bar's channel edges. One transaction per
asset. The history before launch comes from a one-off --backfill: rows are live=false and
pre-marked notified, so history is never pushed to Telegram. The same goes for trades found
while catching up after an outage longer than the fetched window (~35 days): the missed bars
are fetched and replayed exactly, but written as backfill, never as late live calls.

Smart-DCA boost days (sweep_dca): once per FNG day, the accumulator's rule
(strategies/dca_boost.py) on today's Fear & Greed + the latest closed BTC daily bar →
quant.dca_boost_days, with the rule replayed from 2026-01-01 vs a plain DCA. The alert
dispatcher turns boosted days into the "定投加倍日" push.

Env: TIMESCALE_URL (sops). EVAL_INTERVAL seconds between sweeps (default 300).
Run: .venv-bots/bin/python strategies/signal_evaluator.py [--once]
     .venv-bots/bin/python strategies/signal_evaluator.py --backfill 2026-01-01 [--dry-run]
     (--dry-run prints the replayed trades + summary and needs no DB.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from math import prod

import psycopg2
import psycopg2.extras
import requests

import dca_boost
import strategy_record as sr

DSN = os.environ.get("TIMESCALE_URL", "")
INTERVAL = int(os.environ.get("EVAL_INTERVAL", "300"))

_KLINES = "https://api.binance.com/api/v3/klines"
_HOUR_MS = 3_600_000
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

CRYPTO = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK"}
# Core equity set; extended at sweep time with quant.semi_universe symbols (38-ticker
# NVDA supply chain incl. SPY/MSFT/META/GOOGL/AMZN) so the allowed list tracks the DB.
EQUITY_CORE = {"NVDA", "AMD", "QQQ"}
_YF = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
_HDRS = {"User-Agent": "Mozilla/5.0 (quant signal evaluator)"}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


# ---------- market data (closed bars only) ----------

def crypto_closes(asset: str, timeframe: str, limit: int = 1100) -> list[tuple[int, float]]:
    """[(close_time_ms, close), ...] for CLOSED bars, oldest→newest."""
    interval = {"1h": "1h", "1d": "1d"}[timeframe]
    r = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": f"{asset}USDT", "interval": interval, "limit": min(limit, 1000)},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    out = [(int(k[6]), float(k[4])) for k in rows]
    # Drop the still-forming last bar (close_time in the future).
    now_ms = int(time.time() * 1000)
    return [x for x in out if x[0] <= now_ms]


def _closed_hlc(rows: list) -> list[sr.Bar]:
    """Binance kline rows → (close_time_ms, high, low, close) for CLOSED bars only."""
    now_ms = int(time.time() * 1000)
    return [(int(k[6]), float(k[2]), float(k[3]), float(k[4])) for k in rows if int(k[6]) <= now_ms]


def crypto_hlc(asset: str, limit: int = 1000) -> list[sr.Bar]:
    """The latest closed 1h bars (≤ limit-1: the forming bar is dropped), oldest→newest."""
    r = requests.get(_KLINES, params={"symbol": f"{asset}USDT", "interval": "1h",
                                      "limit": min(limit, 1000)}, timeout=15)
    r.raise_for_status()
    return _closed_hlc(r.json())


def crypto_hlc_since(asset: str, start_ms: int) -> list[sr.Bar]:
    """All closed 1h bars opening at/after start_ms, paginated 1000 at a time (backfill)."""
    rows: list = []
    t = start_ms
    while True:
        r = requests.get(_KLINES, params={"symbol": f"{asset}USDT", "interval": "1h",
                                          "startTime": t, "limit": 1000}, timeout=20)
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < 1000:
            return _closed_hlc(rows)
        t = int(page[-1][6]) + 1


def equity_closes(asset: str) -> list[tuple[int, float]]:
    """Daily closes for ANY US stock/ETF: financialdata.net first (10y history, on-disk
    daily cache, budget-guarded — see findata.py), Yahoo fallback (2y, no SLA)."""
    try:
        import findata
        bars = findata.closes_us(asset, min_bars=600)
        if bars:
            return bars
    except Exception:
        pass
    r = requests.get(_YF.format(sym=asset), headers=_HDRS, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts, close = res["timestamp"], res["indicators"]["quote"][0]["close"]
    out = [(int(t) * 1000, float(c)) for t, c in zip(ts, close) if c is not None]
    today = datetime.now(timezone.utc).date()
    return [x for x in out if datetime.fromtimestamp(x[0] / 1000, timezone.utc).date() < today]


def fng_now() -> tuple[int, int]:
    """(unix_ms_of_value, fng_value)"""
    r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
    r.raise_for_status()
    d = r.json()["data"][0]
    return int(d["timestamp"]) * 1000, int(d["value"])


def vix_now() -> tuple[int, float]:
    """(unix_ms_of_bar, vix_close) — latest daily VIX close from Yahoo (^VIX). Unlike the
    bar feeds we DO use the most recent value even if today's session is open: VIX alerts
    are about the fear level right now, and the (signal_id, bar_ts) dedupe still caps one
    fire per VIX bar."""
    r = requests.get(_YF.format(sym="^VIX"), headers=_HDRS, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts, close = res["timestamp"], res["indicators"]["quote"][0]["close"]
    pairs = [(int(t) * 1000, float(c)) for t, c in zip(ts, close) if c is not None]
    return pairs[-1]


# ---------- indicators (plain python — small series, no pandas needed) ----------

def ema_series(closes: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out = [closes[0]]
    for c in closes[1:]:
        out.append(c * k + out[-1] * (1 - k))
    return out


# ---------- evaluation per kind ----------

def eval_ema_cross(bars: list[tuple[int, float]], p: dict) -> dict | None:
    fast_n, slow_n = int(p.get("ema_fast", 20)), int(p.get("ema_slow", 50))
    direction = p.get("direction", "golden")
    if len(bars) < slow_n + 2:
        return None
    closes = [c for _, c in bars]
    f, s = ema_series(closes, fast_n), ema_series(closes, slow_n)
    prev_diff, cur_diff = f[-2] - s[-2], f[-1] - s[-1]
    golden = prev_diff <= 0 < cur_diff
    death = prev_diff >= 0 > cur_diff
    if (golden and direction in ("golden", "both")) or (death and direction in ("death", "both")):
        kind = "golden" if golden else "death"
        return {
            "bar_ts": bars[-1][0],
            "price": closes[-1],
            "direction": kind,
            "message": (f"EMA{fast_n} {'上穿' if golden else '下穿'} EMA{slow_n}"
                        f"({'金叉' if golden else '死叉'}),收盘 {closes[-1]:,.2f}"),
        }
    return None


def eval_donchian(bars: list[tuple[int, float]], p: dict) -> dict | None:
    entry_lb, exit_lb = int(p.get("entry_lb", 168)), int(p.get("exit_lb", 72))
    side = p.get("side", "entry")
    need = max(entry_lb, exit_lb) + 2
    if len(bars) < need:
        return None
    closes = [c for _, c in bars]
    last = closes[-1]
    hi = max(closes[-(entry_lb + 1):-1])  # prior N bars, excluding current
    lo = min(closes[-(exit_lb + 1):-1])
    if last > hi and side in ("entry", "both"):
        return {"bar_ts": bars[-1][0], "price": last, "direction": "entry",
                "message": f"收盘 {last:,.2f} 突破 {entry_lb} 根K线高点 {hi:,.2f}(入场条件)"}
    if last < lo and side in ("exit", "both"):
        return {"bar_ts": bars[-1][0], "price": last, "direction": "exit",
                "message": f"收盘 {last:,.2f} 跌破 {exit_lb} 根K线低点 {lo:,.2f}(离场条件)"}
    return None


def eval_fng(p: dict) -> dict | None:
    below = int(p.get("below", 25))
    ts_ms, val = fng_now()
    if val <= below:
        return {"bar_ts": ts_ms, "price": None, "direction": "fear",
                "value": val,
                "message": f"恐惧贪婪指数 {val} ≤ 你设定的 {below}(市场恐慌区)"}
    return None


def eval_vix(p: dict) -> dict | None:
    above = float(p.get("above", 25))
    ts_ms, val = vix_now()
    if val >= above:
        return {"bar_ts": ts_ms, "price": None, "direction": "fear",
                "value": val,
                "message": f"VIX 恐慌指数 {val:.1f} ≥ 你设定的 {above:g}(美股波动/恐慌升高)"}
    return None


# ---------- sweep ----------

def _is_commodity(asset: str) -> bool:
    try:
        import findata
        return asset in findata.COMMODITIES
    except Exception:
        return False


def commodity_closes(asset: str) -> list[tuple[int, float]]:
    """Daily closes for a continuous commodity future via findata (no Yahoo fallback)."""
    import findata
    return findata.closes_commodity(asset, min_bars=600)


def _is_us_symbol(asset: str) -> bool:
    try:
        import findata
        return findata.is_us_symbol(asset)
    except Exception:
        return False


def equity_allowed(conn) -> set[str]:
    """Core equities + the semi-universe tickers (tracks the DB; cheap query)."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM quant.semi_universe")
            return EQUITY_CORE | {r[0] for r in cur.fetchall()}
    except Exception as e:
        log(f"semi_universe fetch failed (using core set): {e!r}")
        return set(EQUITY_CORE)


def sweep(conn) -> int:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, user_id, name, kind, asset, timeframe, params "
                    "FROM quant.user_signals WHERE status='active'")
        signals = cur.fetchall()
    if not signals:
        return 0
    equities = equity_allowed(conn)

    # Group identical configs → one evaluation each.
    groups: dict[str, dict] = {}
    for s in signals:
        key = json.dumps([s["kind"], s["asset"], s["timeframe"], s["params"]], sort_keys=True)
        groups.setdefault(key, {"spec": s, "members": []})["members"].append(s)

    fired = 0
    cache: dict[str, list[tuple[int, float]]] = {}
    for key, g in groups.items():
        s = g["spec"]
        kind, asset, tf, params = s["kind"], s["asset"], s["timeframe"], s["params"] or {}
        try:
            if kind == "fng_threshold":
                hit = eval_fng(params)
            elif kind == "vix_threshold":
                hit = eval_vix(params)
            else:
                ck = f"{asset}:{tf}"
                if ck not in cache:
                    if asset in CRYPTO:
                        cache[ck] = crypto_closes(asset, tf)
                    elif _is_commodity(asset):
                        cache[ck] = commodity_closes(asset)
                    elif asset in equities or _is_us_symbol(asset):
                        # equities set (semi universe) is the fast path; any other US
                        # ticker is accepted after a findata symbol-list check.
                        cache[ck] = equity_closes(asset)
                    else:
                        log(f"unknown asset {asset!r} (signal {s['id']}) — skipping")
                        cache[ck] = []
                bars = cache[ck]
                if not bars:
                    continue
                hit = eval_ema_cross(bars, params) if kind == "ema_cross" else eval_donchian(bars, params)
        except Exception as e:
            log(f"eval {kind}/{asset}/{tf} failed: {e!r}")
            continue
        if not hit:
            continue

        bar_dt = datetime.fromtimestamp(hit["bar_ts"] / 1000, timezone.utc)
        details = {k: v for k, v in hit.items() if k != "bar_ts"}
        for member in g["members"]:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO quant.signal_fires (signal_id, user_id, bar_ts, details)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (signal_id, bar_ts) DO NOTHING
                           RETURNING id""",
                        (member["id"], member["user_id"], bar_dt, json.dumps(details)),
                    )
                    if cur.fetchone():
                        cur.execute("UPDATE quant.user_signals SET last_fired_at=now() WHERE id=%s",
                                    (member["id"],))
                        fired += 1
                        log(f"FIRE signal {member['id']} ({member['name']!r}): {details['message']}")
            except Exception as e:
                log(f"fire insert for signal {member['id']} failed: {e!r}")
    return fired


# ---------- house strategy (public track record, migration 032) ----------

def _ms_to_dt(ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=ms)  # exact (no float rounding of .999 closes)


def _dt_to_ms(d: datetime) -> int:
    return (d - _EPOCH) // timedelta(milliseconds=1)


def _fmt_ms(ms: int) -> str:
    return _ms_to_dt(ms).strftime("%Y-%m-%d %H:%M")


def _upsert_asset(cur, asset: str, bars: list[sr.Bar], start: sr.Bar | None = None) -> None:
    """Refresh quant.strategy_assets: last close + the next bar's channel edges. start_* (the
    buy&hold baseline) is written only when `start` is given — i.e. by --backfill; the live
    sweep passes None and COALESCE keeps the stored baseline."""
    ch = sr.channels(bars)
    cur.execute(
        """INSERT INTO quant.strategy_assets
             (strategy, asset, last_ts, last_close, channel_high, channel_low,
              start_ts, start_price, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
           ON CONFLICT (strategy, asset) DO UPDATE
             SET last_ts = EXCLUDED.last_ts, last_close = EXCLUDED.last_close,
                 channel_high = EXCLUDED.channel_high, channel_low = EXCLUDED.channel_low,
                 start_ts = coalesce(EXCLUDED.start_ts, strategy_assets.start_ts),
                 start_price = coalesce(EXCLUDED.start_price, strategy_assets.start_price),
                 updated_at = now()""",
        (sr.STRATEGY, asset, _ms_to_dt(ch["last_ts"]), ch["last_close"],
         ch["channel_high"], ch["channel_low"],
         _ms_to_dt(start[0]) if start else None, start[3] if start else None),
    )


def _house_resume(cur, asset: str) -> tuple[dict | None, int, int] | None:
    """Where the live sweep picks up for one asset: (open position, after_ms, processed_ms),
    or None when the asset has no track record yet. after_ms = the last event — bars after
    it were already evaluated without an event, so re-scanning them is idempotent;
    processed_ms = the last bar already evaluated (strategy_assets.last_ts)."""
    key = (sr.STRATEGY, asset)
    cur.execute("SELECT entry_ts, entry_price FROM quant.strategy_signals "
                "WHERE strategy = %s AND asset = %s AND exit_ts IS NULL", key)
    open_row = cur.fetchone()
    cur.execute("SELECT max(coalesce(exit_ts, entry_ts)) FROM quant.strategy_signals "
                "WHERE strategy = %s AND asset = %s", key)
    last_event = cur.fetchone()[0]
    cur.execute("SELECT last_ts FROM quant.strategy_assets "
                "WHERE strategy = %s AND asset = %s", key)
    state = cur.fetchone()
    last_ts = state[0] if state else None
    if last_event is None and last_ts is None:
        return None
    after_ms = _dt_to_ms(last_event or last_ts)
    processed_ms = max(after_ms, _dt_to_ms(last_ts)) if last_ts else after_ms
    position = ({"entry_ts": _dt_to_ms(open_row[0]), "entry_price": float(open_row[1])}
                if open_row else None)
    return position, after_ms, processed_ms


def _gap(bars: list[sr.Bar], processed_ms: int) -> bool:
    """True when the bar after processed_ms has no full entry lookback in `bars`: replaying
    them would skip bars that were never evaluated (evaluator down longer than the window)."""
    return len(bars) > sr.ENTRY_LB and processed_ms < bars[sr.ENTRY_LB - 1][0]


def _sweep_house_asset(conn, asset: str, bars: list[sr.Bar], catch_up: bool = False) -> list[dict]:
    """Apply new house events for one asset and return them. Caller wraps this in a
    transaction. catch_up=True (bars re-fetched across an outage gap): the events are
    history computed after the fact, so they're written like --backfill — live=false and
    pre-marked notified, never pushed or shown as live calls."""
    if len(bars) <= sr.ENTRY_LB:
        raise RuntimeError(f"only {len(bars)} closed bars fetched (need > {sr.ENTRY_LB})")
    key = (sr.STRATEGY, asset)
    with conn.cursor() as cur:
        resume = _house_resume(cur, asset)
        if resume is None:
            log(f"house {asset}: no track record yet — run --backfill first; skipping")
            return []
        position, after_ms, processed_ms = resume
        if _gap(bars, processed_ms):
            # Replaying across never-evaluated bars would invent trades — write nothing.
            raise RuntimeError(
                f"gap — last processed bar {_fmt_ms(processed_ms)} UTC is older than the "
                f"bars given (first evaluable {_fmt_ms(bars[sr.ENTRY_LB][0])} UTC); "
                "nothing written")

        stamp = datetime.now(timezone.utc) if catch_up else None  # notified_at for catch-up rows
        events = sr.step(bars, position, after_ms)
        for ev in events:
            at = _ms_to_dt(ev["ts"])
            if ev["type"] == "entry":
                cur.execute(
                    """INSERT INTO quant.strategy_signals
                         (strategy, asset, entry_ts, entry_price, entry_level, live,
                          entry_notified_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    key + (at, ev["price"], ev["level"], not catch_up, stamp),
                )
            else:
                cur.execute(
                    """UPDATE quant.strategy_signals
                          SET exit_ts = %s, exit_price = %s, exit_level = %s,
                              exit_notified_at = %s
                        WHERE strategy = %s AND asset = %s AND exit_ts IS NULL""",
                    (at, ev["price"], ev["level"], stamp) + key,
                )
                if cur.rowcount != 1:
                    raise RuntimeError(
                        f"exit at {_fmt_ms(ev['ts'])} matched {cur.rowcount} open rows")
        _upsert_asset(cur, asset, bars)
    return events


def sweep_house(conn) -> int:
    """Run the house rule on every sr.ASSETS; returns the number of new events. One
    transaction per asset; a failing asset is logged and retried on the next sweep. If the
    evaluator was down longer than the latest-1000-bar window, the missed bars are fetched
    (so the replay is exact, not a stale position carried across the hole) and what they
    trigger is recorded as backfill — see _sweep_house_asset(catch_up=True)."""
    n = 0
    for asset in sr.ASSETS:
        try:
            bars = crypto_hlc(asset)  # network first — never hold a transaction open on HTTP
            with conn.cursor() as cur:  # autocommit read: no transaction across the refetch
                resume = _house_resume(cur, asset)
            catch_up = resume is not None and _gap(bars, resume[2])
            if catch_up:
                log(f"house {asset}: WARNING gap — last processed bar {_fmt_ms(resume[2])} UTC "
                    f"is older than the fetched window (first evaluable bar "
                    f"{_fmt_ms(bars[sr.ENTRY_LB][0])} UTC). Fetching the missed bars; events "
                    "found in them are recorded as backfill (live=false, never pushed).")
                bars = crypto_hlc_since(asset, resume[2] - (sr.ENTRY_LB + 2) * _HOUR_MS)
            with conn:  # psycopg2 ≥2.9: BEGIN…COMMIT (ROLLBACK on error) even in autocommit
                events = _sweep_house_asset(conn, asset, bars, catch_up)
        except Exception as e:
            log(f"house {sr.STRATEGY}/{asset} failed: {e!r}")
            continue
        for ev in events:  # logged only once committed
            log(f"HOUSE {asset} {ev['type'].upper()} close {ev['price']:,.2f} broke "
                f"{ev['level']:,.2f} (bar {_fmt_ms(ev['ts'])} UTC)"
                + (" [gap catch-up, recorded as backfill]" if catch_up else ""))
        n += len(events)
    return n


def _has_record(conn, asset: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT EXISTS (SELECT 1 FROM quant.strategy_signals
                               WHERE strategy = %s AND asset = %s)
                   OR EXISTS (SELECT 1 FROM quant.strategy_assets
                               WHERE strategy = %s AND asset = %s)""",
            (sr.STRATEGY, asset) * 2,
        )
        return cur.fetchone()[0]


def _write_backfill(conn, asset: str, trades: list[tuple[dict, dict | None]],
                    bars: list[sr.Bar], start: sr.Bar) -> None:
    """History rows are live=false and pre-marked notified: never pushed to Telegram."""
    stamp = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        for entry, exit_ in trades:
            cur.execute(
                """INSERT INTO quant.strategy_signals
                     (strategy, asset, entry_ts, entry_price, entry_level,
                      exit_ts, exit_price, exit_level, live, entry_notified_at, exit_notified_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)""",
                (sr.STRATEGY, asset, _ms_to_dt(entry["ts"]), entry["price"], entry["level"],
                 _ms_to_dt(exit_["ts"]) if exit_ else None,
                 exit_["price"] if exit_ else None,
                 exit_["level"] if exit_ else None,
                 stamp, stamp if exit_ else None),
            )
        _upsert_asset(cur, asset, bars, start=start)


def _print_backfill(asset: str, trades: list[tuple[dict, dict | None]],
                    start: sr.Bar, last: sr.Bar) -> dict:
    """Print the replayed trades + a per-asset summary (fee math mirrors quant.strategy_record)."""
    for entry, exit_ in trades:
        head = f"  {asset} {_fmt_ms(entry['ts'])} {entry['price']:>10,.2f} →"
        if exit_:
            gross = exit_["price"] / entry["price"] - 1
            print(f"{head} {_fmt_ms(exit_['ts'])} {exit_['price']:>10,.2f}  "
                  f"gross {gross:+6.1%}  net {sr.net_return(entry['price'], exit_['price']):+6.1%}")
        else:
            print(f"{head} OPEN (last {last[3]:,.2f}, net if sold "
                  f"{sr.net_return(entry['price'], last[3]):+.1%})")
    closed = [(e, x) for e, x in trades if x]
    nets = [sr.net_return(e["price"], x["price"]) for e, x in closed]
    net_compound = prod(1 + r for r in nets) - 1
    gross_compound = prod(x["price"] / e["price"] for e, x in closed) - 1
    open_entry = trades[-1][0] if trades and trades[-1][1] is None else None
    open_ret = sr.net_return(open_entry["price"], last[3]) if open_entry else 0.0
    sleeve = (1 + net_compound) * (1 + open_ret) - 1
    hold = last[3] / start[3] - 1
    wins = sum(1 for r in nets if r > 0)
    state = (f"OPEN since {_fmt_ms(open_entry['ts'])} UTC @{open_entry['price']:.2f}"
             if open_entry else "flat")
    print(f"{asset}: closed={len(closed)} wins={wins} (net>0) compounded net={net_compound:+.1%} "
          f"(gross {gross_compound:+.1%}) | {state} | sleeve {sleeve:+.1%} vs buy&hold {hold:+.1%} "
          f"(from {start[3]:,.2f} @ {_fmt_ms(start[0])} UTC)")
    return {"closed": len(closed), "wins": wins, "sleeve": sleeve, "hold": hold}


def backfill(start: str, dry_run: bool) -> int:
    """One-off: replay the house rule from `start` (UTC date) and store it as history."""
    start_ms = _dt_to_ms(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    if not dry_run and not DSN:
        print("TIMESCALE_URL required (or pass --dry-run)", file=sys.stderr)
        return 2
    conn = None if dry_run else psycopg2.connect(DSN)
    if conn is not None:
        conn.autocommit = True
    summaries = []
    try:
        for asset in sr.ASSETS:
            if conn is not None and _has_record(conn, asset):
                log(f"backfill {asset}: already has a track record — skipping")
                continue
            # 170h of warm-up so the first bar closing after `start` has a full 168-bar lookback.
            bars = crypto_hlc_since(asset, start_ms - (sr.ENTRY_LB + 2) * _HOUR_MS)
            first = next((b for b in bars if b[0] >= start_ms), None)
            if first is None:
                log(f"backfill {asset}: no closed bar after {start} — skipping")
                continue
            events = sr.step(bars, None, after_ms=start_ms)
            trades: list[tuple[dict, dict | None]] = []
            for ev in events:  # step() alternates entry, exit, entry, … starting flat
                if ev["type"] == "entry":
                    trades.append((ev, None))
                else:
                    trades[-1] = (trades[-1][0], ev)
            summaries.append(_print_backfill(asset, trades, first, bars[-1]))
            if conn is not None:
                with conn:
                    _write_backfill(conn, asset, trades, bars, first)
                log(f"backfill {asset}: wrote {len(trades)} trade(s) (live=false, pre-notified)")
    finally:
        if conn is not None:
            conn.close()
    if summaries:
        n_closed = sum(s["closed"] for s in summaries)
        win_rate = sum(s["wins"] for s in summaries) / n_closed if n_closed else 0.0
        print(f"portfolio (equal-weight, since {start}): strategy "
              f"{sum(s['sleeve'] for s in summaries) / len(summaries):+.1%} vs buy&hold "
              f"{sum(s['hold'] for s in summaries) / len(summaries):+.1%} | "
              f"{n_closed} closed trades, win rate {win_rate:.0%}"
              + (" | DRY RUN — nothing written" if dry_run else ""))
    return 0


# ---------- smart-DCA boost days ----------

DCA_FROM = "2026-01-01"


def btc_days(start: str) -> list[tuple[str, float, float]]:
    """Closed BTC daily bars opening on/after `start` (≤1000, one request): (day, high, close)."""
    start_ms = _dt_to_ms(datetime.fromisoformat(start).replace(tzinfo=timezone.utc))
    r = requests.get(_KLINES, params={"symbol": "BTCUSDT", "interval": "1d",
                                      "startTime": start_ms, "limit": 1000}, timeout=20)
    r.raise_for_status()
    return [(f"{_ms_to_dt(int(k[0])):%Y-%m-%d}", h, c)
            for k, (_ts, h, _l, c) in zip(r.json(), _closed_hlc(r.json()))]


def fng_days(limit: int = 400) -> dict[str, int]:
    """Fear & Greed by UTC date, newest first as published by alternative.me."""
    r = requests.get("https://api.alternative.me/fng/", params={"limit": limit}, timeout=15)
    r.raise_for_status()
    return {f"{_ms_to_dt(int(d['timestamp']) * 1000):%Y-%m-%d}": int(d["value"])
            for d in r.json()["data"]}


def sweep_dca(conn) -> bool:
    """One quant.dca_boost_days row per FNG day; returns True when a new row was written.
    Cheap when today's row exists: a single FNG request, no BTC fetch."""
    fng = fng_days()
    today = max(fng)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM quant.dca_boost_days WHERE day = %s", (today,))
        if cur.fetchone():
            return False
    warm = f"{datetime.fromisoformat(DCA_FROM) - timedelta(days=dca_boost.DIP_LOOKBACK + 5):%Y-%m-%d}"
    bars = btc_days(warm)
    # Days without a published FNG are neutral (50), matching FngSeries' default.
    days = [(d, fng.get(d, 50), h, c) for d, h, c in bars]
    bar_day, _f, _h, close = days[-1]
    u = dca_boost.units(fng[today], close, [d[2] for d in days[-dca_boost.DIP_LOOKBACK:]])
    sim = dca_boost.simulate(days, DCA_FROM) or {}
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO quant.dca_boost_days
                 (day, fng, bar_day, btc_close, high_30d, drawdown, units, fear_add, dip_add,
                  ytd_days, ytd_boosted_days, ytd_plain_cost, ytd_smart_cost)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (day) DO NOTHING""",
            (today, fng[today], bar_day, close, u["high_30d"], u["drawdown"], u["units"],
             u["fear_add"], u["dip_add"], sim.get("days"), sim.get("boosted_days"),
             sim.get("plain_cost"), sim.get("smart_cost")))
    log(f"DCA day {today}: FNG {fng[today]}, BTC {close:,.0f} ({bar_day}) → ×{u['units']:g}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="User-signal + house-strategy evaluator.")
    ap.add_argument("--once", action="store_true", help="run a single sweep and exit")
    ap.add_argument("--backfill", metavar="YYYY-MM-DD",
                    help="one-off: replay the house strategy from this UTC date as history")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --backfill: print trades + summary, write nothing (no DB needed)")
    args = ap.parse_args()
    if args.dry_run and not args.backfill:
        ap.error("--dry-run only applies to --backfill")
    if args.backfill:
        return backfill(args.backfill, dry_run=args.dry_run)
    if not DSN:
        print("TIMESCALE_URL required", file=sys.stderr)
        return 2
    log(f"signal evaluator up (interval={INTERVAL}s, once={args.once})")
    while True:
        conn = None
        try:
            conn = psycopg2.connect(DSN)
            conn.autocommit = True
            n = sweep(conn)
            if n:
                log(f"sweep complete: {n} fire(s)")
        except Exception as e:
            log(f"sweep error (continuing): {e!r}")
        # Every iteration, independent of user signals: sweep() returns early when there are
        # none, and a user-signal failure must not starve the public track record.
        if conn is not None:
            try:
                h = sweep_house(conn)
                if h:
                    log(f"house sweep complete: {h} new event(s)")
            except Exception as e:
                log(f"house sweep error (continuing): {e!r}")
            try:
                sweep_dca(conn)
            except Exception as e:
                log(f"dca sweep error (continuing): {e!r}")
            finally:
                conn.close()
        if args.once:
            return 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
