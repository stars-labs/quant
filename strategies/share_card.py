"""Shareable PNG cards for the house strategy — forwarded in Telegram groups, so each card
has to stand alone: the number, what it is, the honest comparison, and the link.

render_exit_card(trade, record)   one closed trade (a strategy_trades row + strategy_record)
render_scorecard(record, as_of)   the since-start record (Monday scorecard)

Numbers come from the same view rows the text messages use (quant.strategy_record is the
single source of stats). Font: SHARE_CARD_FONT (Noto Sans CJK; the variable .ttc is fine) or
`fc-match` — a font without CJK glyphs would render boxes, so a missing font is an error and
the caller falls back to text.
"""

from __future__ import annotations

import io
import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 675
BG = (18, 16, 31)
PANEL = (28, 25, 46)
TEXT = (237, 234, 246)
MUTED = (154, 148, 184)
GREEN = (61, 220, 132)
RED = (255, 90, 110)
ACCENT = (255, 154, 60)
SITE = "starslab.qzz.io/record"
FOOT = "收益已扣买卖各 0.1% 手续费 · 规则模拟信号,不构成投资建议"


@lru_cache(maxsize=1)
def _font_path() -> str:
    path = os.environ.get("SHARE_CARD_FONT")
    if not path:
        path = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK SC:bold"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    if not path or not os.path.exists(path):
        raise RuntimeError("no CJK font: set SHARE_CARD_FONT")
    return path


@lru_cache(maxsize=32)
def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    path = _font_path()
    # .ttc collections: face 2 is Simplified Chinese in Noto Sans CJK.
    f = ImageFont.truetype(path, size, index=2 if path.endswith(".ttc") else 0)
    try:
        f.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass  # static font: one weight only
    return f


def _money(x: float) -> str:
    return f"${x:,.2f}" if x < 1000 else f"${x:,.0f}"


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _md(ts: datetime) -> str:
    ts = ts.astimezone(timezone.utc)
    return f"{ts.month}/{ts.day}"


def _portfolio(record: list[dict]) -> dict:
    n = len(record)
    closed = sum(r["n_closed"] for r in record)
    best = max((r for r in record if r["best_ret"] is not None),
               key=lambda r: r["best_ret"], default=None)
    return {
        "ret": sum(r["sleeve_ret"] for r in record) / n if n else 0.0,
        "hold": sum(r["hold_ret"] for r in record) / n if n else 0.0,
        "closed": closed,
        "win_rate": sum(r["n_wins"] for r in record) / closed if closed else 0.0,
        "best": (best["asset"], best["best_ret"]) if best else None,
        "start": min((r["start_ts"] for r in record if r["start_ts"]), default=None),
    }


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)
    return img, d


def _footer(d: ImageDraw.ImageDraw, record: list[dict]) -> None:
    p = _portfolio(record)
    d.rounded_rectangle([60, 470, W - 60, 590], radius=18, fill=PANEL)
    start = f"{p['start']:%Y-%m-%d} 起" if p["start"] else "至今"
    d.text((90, 490), f"{start} · $1,000 平均分给 {'/'.join(r['asset'] for r in record)}",
           font=_font(24), fill=MUTED)
    follow = f"跟随全部信号 ${1000 * (1 + p['ret']):,.0f}"
    d.text((90, 528), follow, font=_font(34, "Bold"), fill=GREEN if p["ret"] >= 0 else RED)
    x = 90 + d.textlength(follow, font=_font(34, "Bold")) + 40
    d.text((x, 532), f"同期买入持有 ${1000 * (1 + p['hold']):,.0f}", font=_font(30), fill=TEXT)
    d.text((60, 614), SITE, font=_font(26, "Bold"), fill=ACCENT)
    d.text((W - 60, 618), FOOT, font=_font(20), fill=MUTED, anchor="ra")


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_exit_card(t: dict, record: list[dict]) -> bytes:
    img, d = _canvas()
    d.text((60, 44), "趋势突破策略 · 规则模拟信号", font=_font(26), fill=MUTED)
    d.text((60, 92), f"{t['asset']} 跌破离场", font=_font(56, "Bold"), fill=TEXT)
    ret = t["net_ret"]
    d.text((60, 172), _pct(ret), font=_font(150, "Black"), fill=GREEN if ret >= 0 else RED)
    d.text((60, 370),
           f"{_md(t['entry_ts'])} {_money(t['entry_price'])} 买入  →  "
           f"{_md(t['exit_ts'])} {_money(t['exit_price'])} 卖出  ·  持有 {float(t['hold_days']):.1f} 天",
           font=_font(30), fill=TEXT)
    if not t["live"]:
        d.text((60, 418), "这笔的买入在服务上线前,为按规则回溯计算", font=_font(22), fill=MUTED)
    _footer(d, record)
    return _png(img)


def render_scorecard(record: list[dict], as_of: datetime) -> bytes:
    p = _portfolio(record)
    img, d = _canvas()
    d.text((60, 44), f"趋势突破策略 · 战绩  {as_of.astimezone(timezone.utc):%Y-%m-%d}",
           font=_font(26), fill=MUTED)
    d.text((60, 92), "跟随全部信号 vs 买入持有", font=_font(52, "Bold"), fill=TEXT)
    y = 180
    for label, val, big in (("跟随全部信号", p["ret"], True), ("同期买入持有", p["hold"], False)):
        d.text((60, y + 20), label, font=_font(30), fill=MUTED)
        d.text((330, y), _pct(val), font=_font(84 if big else 64, "Black" if big else "Bold"),
               fill=GREEN if val >= 0 else RED)
        y += 110
    stats = f"已平仓 {p['closed']} 笔 · 胜率 {p['win_rate'] * 100:.0f}%"
    if p["best"]:
        stats += f" · 最大一笔 {p['best'][0]} {_pct(p['best'][1])}"
    d.text((60, 402), stats, font=_font(28), fill=TEXT)
    held = [f"{r['asset']} 持有 {_pct(r['open_ret'])}" if r["open_entry_ts"] else f"{r['asset']} 空仓"
            for r in record]
    d.text((60, 438), "  ·  ".join(held), font=_font(24), fill=MUTED)
    _footer(d, record)
    return _png(img)
