"""Unit tests for the house-strategy Telegram messages (migration 032).

Covers strategies/alert_dispatcher.py (entry/exit cards, weekly scorecard, fan-out ordering
and notified-marking, the Monday/ISO-week gate) and the operator daily-report block in
strategies/telegram_alerts.py. Pure: rows are plain dicts shaped like quant.strategy_record /
quant.strategy_trades, and the DB/Telegram helpers are swapped for fakes — no DB, no network.

Plain test_* functions with bare asserts — runs under pytest or the stdlib harness:
  P=nautilus_equity/.venv/bin/python
  $P -c "import sys; sys.path.insert(0,'tests'); import test_alert_dispatcher as t; \
[getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Strategy modules live in strategies/ at the repo root and have no __init__.py.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "strategies"))

import alert_dispatcher as ad  # noqa: E402
import telegram_alerts as ta  # noqa: E402
from strategy_record import net_return  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 13, 5, tzinfo=UTC)
LINK = "👉 全部信号与实时持仓:https://starslab.qzz.io/record"
DISCLAIMER = "\n\n⚠️ 规则模拟信号,不构成投资建议。"


def bar_close(y: int, mo: int, d: int, h: int) -> datetime:
    """A Binance 1h close_time: hh:59:59.999 UTC (displayed as the next round hour)."""
    return datetime(y, mo, d, h, 59, 59, 999000, tzinfo=UTC)


START = bar_close(2026, 1, 1, 0)
LAST = bar_close(2026, 9, 25, 12)


def rec(asset: str, **kw) -> dict:
    """A quant.strategy_record row: flat, no trades, unless overridden."""
    row = {
        "strategy": "donchian_1h", "asset": asset,
        "start_ts": START, "start_price": 100.0, "last_ts": LAST, "last_close": 100.0,
        "channel_high": 110.0, "channel_low": 90.0,
        "n_closed": 0, "n_wins": 0, "closed_compound": 0.0,
        "best_ret": None, "avg_win": None, "avg_loss": None,
        "open_entry_ts": None, "open_entry_price": None, "open_live": None, "open_ret": None,
        "sleeve_ret": 0.0, "hold_ret": 0.0,
    }
    row.update(kw)
    return row


def record_now() -> list[dict]:
    """The local-harness record on 2026-09-25 (backfill since 2026-01-01)."""
    return [
        rec("BTC", last_close=84471.8, channel_high=87395.67, channel_low=82874.93,
            n_closed=14, n_wins=4, best_ret=0.2134, sleeve_ret=0.0658, hold_ret=-0.0380),
        rec("ETH", last_close=2717.72, channel_high=2807.34, channel_low=2600.15,
            n_closed=13, n_wins=6, best_ret=0.2244,
            open_entry_ts=bar_close(2026, 9, 18, 19), open_entry_price=2636.71,
            open_live=False, open_ret=0.0287, sleeve_ret=-0.0592, hold_ret=-0.0880),
        rec("SOL", last_close=120.74, channel_high=122.33, channel_low=112.52,
            n_closed=11, n_wins=4, best_ret=0.2951,
            open_entry_ts=bar_close(2026, 9, 18, 4), open_entry_price=105.82,
            open_live=False, open_ret=0.1387, sleeve_ret=0.1423, hold_ret=-0.0352),
    ]


def trade(asset: str, entry_ts: datetime, entry_price: float, entry_level: float,
          exit_ts: datetime | None = None, exit_price: float | None = None,
          exit_level: float | None = None, live: bool = True, id: int = 1,
          entry_notified: bool = False, exit_notified: bool = False) -> dict:
    """A quant.strategy_trades row (net_ret / hold_days computed like the view)."""
    end = exit_ts or NOW
    return {
        "id": id, "strategy": "donchian_1h", "asset": asset,
        "entry_ts": entry_ts, "entry_price": entry_price, "entry_level": entry_level,
        "exit_ts": exit_ts, "exit_price": exit_price, "exit_level": exit_level,
        "live": live,
        "entry_notified_at": NOW if entry_notified else None,
        "exit_notified_at": NOW if exit_notified else None,
        "created_at": NOW,
        "net_ret": net_return(entry_price, exit_price) if exit_ts else None,
        "hold_days": Decimal(str(round((end - entry_ts).total_seconds() / 86400, 1))),
    }


@contextmanager
def patched(mod, **attrs):
    old = {k: getattr(mod, k) for k in attrs}
    for k, v in attrs.items():
        setattr(mod, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(mod, k, v)


# ---------- portfolio roll-up ----------

def test_portfolio_is_equal_weight_average_of_sleeves():
    p = ad.portfolio(record_now())
    assert round(p["ret"], 4) == round((0.0658 - 0.0592 + 0.1423) / 3, 4)


def test_portfolio_hold_is_equal_weight_average():
    p = ad.portfolio(record_now())
    assert round(p["hold_ret"], 4) == round((-0.0380 - 0.0880 - 0.0352) / 3, 4)


def test_portfolio_win_rate_is_pooled_over_all_closed_trades():
    p = ad.portfolio(record_now())
    assert (p["n_wins"], p["n_closed"], round(p["win_rate"], 4)) == (14, 38, round(14 / 38, 4))


def test_portfolio_best_trade_names_its_asset():
    p = ad.portfolio(record_now())
    assert (p["best_asset"], p["best_ret"]) == ("SOL", 0.2951)


def test_portfolio_without_closed_trades_has_no_win_rate_or_best():
    p = ad.portfolio([rec("BTC"), rec("ETH")])
    assert (p["n_closed"], p["win_rate"], p["best_ret"], p["best_asset"]) == (0, None, None, None)


# ---------- entry card ----------

def btc_entry() -> dict:
    return trade("BTC", LAST, 88000.0, 87395.67, id=41)


def record_btc_long() -> list[dict]:
    r = record_now()
    r[0].update(open_entry_ts=LAST, open_entry_price=88000.0, open_live=True,
                open_ret=net_return(88000.0, 88000.0), last_close=88000.0)
    return r


def test_entry_card_full_text():
    assert ad.format_entry(btc_entry(), record_btc_long(), NOW) == (
        "🟢 <b>策略信号 · BTC 突破买入</b>\n"
        "1 小时收盘 $88,000.00(9/25 13:00 UTC),突破过去 7 天最高点 $87,395.67\n"
        "离场规则:1 小时收盘跌破过去 3 天最低点(当前 $82,874.93,距现价 -5.8%)\n"
        "提示:趋势信号约 6 成会亏损离场,赚钱靠少数大行情(今年最大一笔 SOL +29.5%)。\n"
        + LINK + DISCLAIMER
    )


def test_entry_card_for_already_closed_trade_omits_current_exit_level():
    # Both legs pending (dispatcher was down): "当前 $X" would describe a later position.
    t = trade("BTC", LAST - timedelta(hours=5), 88000.0, 87395.67,
              exit_ts=LAST, exit_price=86000.0, exit_level=86500.0)
    text = ad.format_entry(t, record_now(), NOW)
    assert "离场规则:1 小时收盘跌破过去 3 天最低点\n" in text


def test_entry_card_without_closed_trades_has_no_hint_line():
    record = [rec("BTC", open_entry_ts=LAST, open_entry_price=88000.0, open_live=True,
                  open_ret=0.0, last_close=88000.0), rec("ETH"), rec("SOL")]
    assert "提示" not in ad.format_entry(btc_entry(), record, NOW)


def test_entry_hint_when_most_trades_win_states_win_share():
    record = [rec("BTC", n_closed=10, n_wins=7, best_ret=0.12)]
    assert "提示:历史上约 7 成信号盈利离场(今年最大一笔 BTC +12.0%)。" in \
        ad.format_entry(btc_entry(), record, NOW)


def test_entry_hint_names_start_date_when_record_did_not_start_this_year():
    record = [rec("BTC", n_closed=4, n_wins=1, best_ret=0.2, start_ts=bar_close(2026, 3, 1, 0))]
    assert "2026-03-01 以来最大一笔 BTC +20.0%" in ad.format_entry(btc_entry(), record, NOW)


# ---------- exit card ----------

def eth_trade(live: bool = True) -> dict:
    return trade("ETH", bar_close(2026, 8, 19, 12), 1937.21, 1930.00,
                 exit_ts=bar_close(2026, 9, 2, 9), exit_price=2376.61, exit_level=2390.00,
                 live=live, id=7)


def test_exit_card_full_text():
    assert ad.format_exit(eth_trade()) == (
        "🔴 <b>策略信号 · ETH 跌破离场</b>\n"
        "1 小时收盘 $2,376.61(9/2 10:00 UTC),跌破过去 3 天最低点 $2,390.00\n"
        "本次 8/19 $1,937.21 → 9/2 $2,376.61,+22.4%(已扣手续费),持有 13.9 天\n"
        + LINK + DISCLAIMER
    )


def test_exit_card_of_backfilled_entry_says_the_entry_was_backfilled():
    assert "(这笔的买入在服务上线前,是按规则回溯计算的,当时没有推送)" in \
        ad.format_exit(eth_trade(live=False))


def test_exit_card_shows_losses_with_sign():
    t = trade("SOL", bar_close(2026, 9, 1, 0), 200.0, 199.0,
              exit_ts=bar_close(2026, 9, 3, 0), exit_price=190.0, exit_level=191.0)
    assert ",-5.2%(已扣手续费),持有 2 天" in ad.format_exit(t)


# ---------- weekly scorecard ----------

BACKFILLED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)


def btc_recent() -> list[dict]:
    return [trade("BTC", bar_close(2026, 9, 18, 13), 75000.0, 74900.0,
                  exit_ts=bar_close(2026, 9, 24, 9), exit_price=78000.0, exit_level=78100.0,
                  live=False, entry_notified=True, exit_notified=True)]


def test_weekly_scorecard_full_text():
    assert ad.format_weekly_scorecard(record_now(), btc_recent(), BACKFILLED_AT) == (
        "📊 <b>趋势突破策略 · 每周战绩</b>\n"
        "数据截至 9/25 13:00 UTC\n"
        "\n<b>当前持有</b>\n"
        "ETH:9/18 $2,636.71 买入 → 现价 $2,717.72,浮动 +2.9%(回溯计算)\n"
        "  离场线 $2,600.15(距现价 -4.3%)\n"
        "SOL:9/18 $105.82 买入 → 现价 $120.74,浮动 +13.9%(回溯计算)\n"
        "  离场线 $112.52(距现价 -6.8%)\n"
        "\n<b>空仓等待</b>\n"
        "BTC:现价 $84,471.80,1 小时收盘突破 $87,395.67(距现价 +3.5%)触发买入信号\n"
        "\n<b>近 7 天平仓</b>\n"
        "BTC:9/18 → 9/24,+3.8%(回溯计算)\n"
        "\n<b>2026-01-01 至今</b>\n"
        "$1,000 平均分给 BTC/ETH/SOL 跟随全部信号 → $1,050(+5.0%)\n"
        "同期买入持有 → $946(-5.4%)\n"
        "已平仓 38 笔,胜率 37%,最大一笔 SOL +29.5%\n"
        "收益已扣买卖各 0.1% 手续费;9/25 服务上线前的记录是按规则回溯计算的,不是当时的实时推送。\n"
        "\n" + LINK + DISCLAIMER
    )


def test_weekly_scorecard_without_open_positions_has_no_holding_section():
    record = [rec("BTC", n_closed=2, n_wins=1, best_ret=0.05), rec("ETH"), rec("SOL")]
    text = ad.format_weekly_scorecard(record, [], None)
    assert "当前持有" not in text and text.count("触发买入信号") == 3


def test_weekly_scorecard_without_recent_closes_says_none():
    text = ad.format_weekly_scorecard(record_now(), [], BACKFILLED_AT)
    assert "<b>近 7 天平仓</b>\n无\n" in text


def test_weekly_scorecard_without_closed_trades_says_so_instead_of_win_rate():
    text = ad.format_weekly_scorecard([rec("BTC"), rec("ETH"), rec("SOL")], [], None)
    assert "暂无已平仓交易" in text and "胜率" not in text


def test_weekly_scorecard_shows_strategy_losing_to_buy_and_hold():
    record = [rec("BTC", n_closed=3, n_wins=0, best_ret=-0.01, sleeve_ret=-0.10, hold_ret=0.10)]
    text = ad.format_weekly_scorecard(record, [], None)
    assert ("跟随全部信号 → $900(-10.0%)\n同期买入持有 → $1,100(+10.0%)\n"
            "已平仓 3 笔,胜率 0%,最大一笔 BTC -1.0%") in text


def test_weekly_scorecard_without_backfill_has_no_backfill_note():
    text = ad.format_weekly_scorecard(record_now(), [], None)
    assert "收益已扣买卖各 0.1% 手续费。" in text and "回溯" not in text.split("至今")[1]


def test_every_strategy_message_ends_with_the_disclaimer():
    texts = [ad.format_entry(btc_entry(), record_btc_long(), NOW), ad.format_exit(eth_trade()),
             ad.format_weekly_scorecard(record_now(), btc_recent(), BACKFILLED_AT)]
    assert all(t.endswith(DISCLAIMER) for t in texts)


# ---------- fan-out: ordering, marking, zero subscribers ----------

def run_fan_out(rows: list[dict], chats: list[int], reachable=lambda chat: True):
    """Returns (every send attempt, every leg marked). reachable(chat) = send()'s result."""
    sent, marked = [], []
    with patched(ad, pending_strategy_trades=lambda conn: rows,
                 load_record=lambda conn: record_now(),
                 subscribers=lambda conn, topic: chats,
                 send=lambda chat, text: sent.append((chat, text)) or reachable(chat),
                 mark_notified=lambda conn, tid, leg: marked.append((tid, leg)),
                 render_card=lambda *a: None,  # text path; the photo path has its own tests
                 log=lambda msg: None):
        ad.fan_out_strategy_signals(None, now=NOW)
    return sent, marked


def test_fan_out_with_zero_subscribers_sends_nothing_but_marks_every_leg():
    rows = [trade("BTC", LAST - timedelta(hours=9), 88000.0, 87395.67,
                  exit_ts=LAST, exit_price=86000.0, exit_level=86500.0, id=3)]
    assert run_fan_out(rows, []) == ([], [(3, "entry"), (3, "exit")])


def test_fan_out_sends_entry_then_exit_to_each_subscriber():
    rows = [trade("BTC", LAST - timedelta(hours=9), 88000.0, 87395.67,
                  exit_ts=LAST, exit_price=86000.0, exit_level=86500.0, id=3)]
    sent, _ = run_fan_out(rows, [11, 22])
    assert [(c, "突破买入" in t) for c, t in sent] == [(11, True), (22, True), (11, False), (22, False)]


def test_fan_out_orders_legs_by_time_across_trades():
    early_entry_late_exit = trade("ETH", LAST - timedelta(hours=10), 2700.0, 2690.0,
                                  exit_ts=LAST, exit_price=2600.0, exit_level=2610.0, id=5)
    middle_entry = trade("SOL", LAST - timedelta(hours=4), 120.0, 119.0, id=6)
    _, marked = run_fan_out([middle_entry, early_entry_late_exit], [1])
    assert marked == [(5, "entry"), (6, "entry"), (5, "exit")]


def test_fan_out_skips_notified_entry_of_live_row_and_sends_pending_exit():
    rows = [trade("BTC", LAST - timedelta(hours=9), 88000.0, 87395.67, exit_ts=LAST,
                  exit_price=86000.0, exit_level=86500.0, id=3, entry_notified=True)]
    assert run_fan_out(rows, [1])[1] == [(3, "exit")]


def test_fan_out_never_sends_entry_of_backfilled_row():
    rows = [trade("ETH", bar_close(2026, 9, 18, 19), 2636.71, 2600.0, exit_ts=LAST,
                  exit_price=2590.0, exit_level=2600.15, live=False, id=9)]
    assert run_fan_out(rows, [1])[1] == [(9, "exit")]


def test_fan_out_leaves_legs_pending_when_no_subscriber_was_reached():
    rows = [trade("BTC", LAST - timedelta(hours=9), 88000.0, 87395.67,
                  exit_ts=LAST, exit_price=86000.0, exit_level=86500.0, id=3)]
    sent, marked = run_fan_out(rows, [11, 22], reachable=lambda chat: False)
    # Nothing marked, and the exit isn't attempted before its entry got through.
    assert (marked, [c for c, _ in sent]) == ([], [11, 22])


def test_fan_out_marks_leg_that_reached_at_least_one_subscriber():
    rows = [trade("BTC", LAST - timedelta(hours=9), 88000.0, 87395.67,
                  exit_ts=LAST, exit_price=86000.0, exit_level=86500.0, id=3)]
    _, marked = run_fan_out(rows, [11, 22], reachable=lambda chat: chat == 22)
    assert marked == [(3, "entry"), (3, "exit")]


# ---------- weekly gate ----------

MONDAY = datetime(2026, 9, 28, 0, 1, tzinfo=UTC)


def run_weekly(state: dict, now: datetime, record: list[dict] | None = None,
               reachable: bool = True) -> list:
    sent = []
    with patched(ad, load_record=lambda conn: record_now() if record is None else record,
                 recent_closed=lambda conn, since: [],
                 backfilled_at=lambda conn: BACKFILLED_AT,
                 subscribers=lambda conn, topic: [1],
                 send=lambda chat, text: sent.append(text) or reachable,
                 render_card=lambda *a: None,
                 log=lambda msg: None):
        ad.fan_out_weekly_scorecard(None, state, now=now)
    return sent


def test_weekly_sends_on_monday_and_records_the_iso_week():
    state: dict = {}
    assert (len(run_weekly(state, MONDAY)), state) == (1, {"last_scorecard_week": "2026-W40"})


def test_weekly_sends_once_per_iso_week():
    state: dict = {}
    run_weekly(state, MONDAY)
    assert run_weekly(state, MONDAY + timedelta(hours=12)) == []


def test_weekly_does_not_send_on_other_weekdays():
    assert [len(run_weekly({}, MONDAY + timedelta(days=d))) for d in range(1, 7)] == [0] * 6


def test_weekly_sends_again_next_monday():
    state: dict = {}
    run_weekly(state, MONDAY)
    assert len(run_weekly(state, MONDAY + timedelta(days=7))) == 1


def test_weekly_skips_empty_record_and_keeps_the_week_open():
    state: dict = {}
    assert (run_weekly(state, MONDAY, record=[]), state) == ([], {})


def test_weekly_keeps_the_week_open_when_no_subscriber_was_reached():
    state: dict = {}
    run_weekly(state, MONDAY, reachable=False)
    assert state == {}


# ---------- operator daily report (telegram_alerts.py, English, Markdown) ----------

def test_daily_strategy_block_full_text():
    assert ta.format_strategy_block(record_now()) == (
        "\n*Strategy record* (last bar 09-25 13:00 UTC):\n"
        "  BTC: flat (+3.5% to trigger)\n"
        "  ETH: long +2.9% (since 09-18, backfilled)\n"
        "  SOL: long +13.9% (since 09-18, backfilled)\n"
        "  Portfolio +5.0% vs hold -5.4% since 2026-01-01\n"
        "  Trades: 38 closed, win rate 37%"
    )


def test_daily_strategy_block_live_position_has_no_backfilled_tag():
    record = [rec("BTC", open_entry_ts=LAST, open_entry_price=100.0, open_live=True, open_ret=0.05)]
    assert "  BTC: long +5.0% (since 09-25)\n" in ta.format_strategy_block(record)


def test_daily_strategy_block_without_closed_trades():
    assert ta.format_strategy_block([rec("BTC")]).endswith("  Trades: none closed yet")


def test_daily_strategy_block_is_empty_without_rows():
    assert ta.format_strategy_block([]) == ""


def test_daily_strategy_block_needs_a_dsn():
    assert ta.strategy_record_block("") == ""


# ---------- share cards: broadcast (photo once, file_id reuse, text fallback) ----------

def run_broadcast(chats, text, card, caption=None, photo_ok=lambda chat: True,
                  text_ok=lambda chat: True):
    calls = []

    def fake_photo(chat, photo, cap):
        calls.append(("photo", chat, photo if isinstance(photo, str) else "<png>", cap))
        return f"fid-{chat}" if photo_ok(chat) else None

    def fake_send(chat, t):
        calls.append(("text", chat, t))
        return text_ok(chat)

    with patched(ad, send_photo=fake_photo, send=fake_send, log=lambda msg: None):
        n = ad.broadcast(chats, text, card, caption)
    return n, calls


def test_broadcast_uploads_card_once_then_reuses_file_id():
    n, calls = run_broadcast([1, 2], "T", b"png")
    assert n == 2
    assert calls == [("photo", 1, "<png>", "T"), ("photo", 2, "fid-1", "T")]


def test_broadcast_falls_back_to_text_when_photo_fails():
    n, calls = run_broadcast([1], "T", b"png", photo_ok=lambda chat: False)
    assert n == 1 and calls == [("photo", 1, "<png>", "T"), ("text", 1, "T")]


def test_broadcast_with_caption_sends_photo_then_full_text():
    n, calls = run_broadcast([1], "LONG", b"png", caption="C")
    assert n == 1 and calls == [("photo", 1, "<png>", "C"), ("text", 1, "LONG")]


def test_broadcast_without_card_is_plain_text():
    n, calls = run_broadcast([1, 2], "T", None, text_ok=lambda chat: chat == 2)
    assert n == 1 and calls == [("text", 1, "T"), ("text", 2, "T")]


def test_exit_leg_goes_out_as_card_with_the_exit_text_as_caption():
    rows = [trade("BTC", LAST - timedelta(hours=9), 88000.0, 87395.67,
                  exit_ts=LAST, exit_price=86000.0, exit_level=86500.0, id=3,
                  entry_notified=True)]
    photos = []
    with patched(ad, pending_strategy_trades=lambda conn: rows,
                 load_record=lambda conn: record_now(),
                 subscribers=lambda conn, topic: [7],
                 render_card=lambda fn, *a: fn.encode(),
                 send_photo=lambda chat, photo, cap: photos.append((photo, cap)) or "fid",
                 send=lambda chat, text: False,
                 mark_notified=lambda conn, tid, leg: None,
                 log=lambda msg: None):
        ad.fan_out_strategy_signals(None, now=NOW)
    assert photos == [(b"render_exit_card", ad.format_exit(rows[0]))]


# ---------- smart-DCA boost days ----------

def boost_row(day, units=4.0, fng=20, fear_add=3.0, dip_add=0.0, drawdown=-0.12):
    from datetime import date
    return {"day": date.fromisoformat(day), "fng": fng, "units": units, "fear_add": fear_add,
            "dip_add": dip_add, "btc_close": 70000.0, "high_30d": 79545.45,
            "drawdown": drawdown, "ytd_days": 268, "ytd_boosted_days": 137,
            "ytd_plain_cost": 71884.76, "ytd_smart_cost": 68943.48}


def test_boost_not_due_on_a_plain_day():
    assert not ad.boost_push_due(boost_row("2026-09-27", units=1.0, fear_add=0.0), None)


def test_boost_due_when_never_pushed():
    assert ad.boost_push_due(boost_row("2026-09-27"), None)


def test_boost_suppressed_within_seven_days_at_same_multiple():
    assert not ad.boost_push_due(boost_row("2026-09-27"), boost_row("2026-09-21"))


def test_boost_due_again_after_seven_days():
    assert ad.boost_push_due(boost_row("2026-09-28"), boost_row("2026-09-21"))


def test_boost_due_when_multiple_goes_up():
    assert ad.boost_push_due(boost_row("2026-09-23", units=6.0, fng=12, fear_add=5.0),
                             boost_row("2026-09-21"))


def test_format_dca_boost_fear_only():
    text = ad.format_dca_boost(boost_row("2026-09-27"))
    assert text.startswith("🟢 <b>今天是定投加倍日 · BTC</b>\n恐惧贪婪指数 20(恐慌)\n")
    assert "按规则,今天这笔定投 ×4(基础 1 份 + 恐慌加 3 份)" in text
    assert "平均成本 $68,943,比每天固定金额定投($71,885)低 4.1%;268 天里有 137 天是加倍日" in text
    assert "https://starslab.qzz.io/dca" in text and text.endswith(DISCLAIMER)


def test_format_dca_boost_deep_fear_and_dip():
    text = ad.format_dca_boost(boost_row("2026-09-27", units=8.0, fng=10, fear_add=5.0,
                                         dip_add=2.0, drawdown=-0.25))
    assert "(极度恐慌)" in text
    assert "×8(基础 1 份 + 极度恐慌加 5 份 + 大跌加 2 份)" in text


def run_boost(rows, last_pushed, chats, now, reachable=True):
    sent, updates = [], []

    class Cur:
        def __init__(self):
            self.q = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            self.q = sql
            if sql.startswith("UPDATE"):
                updates.append(params)

        def fetchall(self):
            return rows

        def fetchone(self):
            return last_pushed

    class Conn:
        def cursor(self, cursor_factory=None):
            return Cur()

    with patched(ad, subscribers=lambda conn, topic: chats,
                 send=lambda chat, text: sent.append(text) or reachable,
                 log=lambda msg: None):
        ad.fan_out_dca_boost(Conn(), now=now)
    return sent, updates


def test_fan_out_boost_pushes_today_and_marks_pushed():
    from datetime import date
    sent, updates = run_boost([boost_row("2026-09-27")], None, [1], NOW.replace(day=27))
    assert len(sent) == 1 and updates == [(True, date(2026, 9, 27))]


def test_fan_out_boost_never_pushes_stale_rows():
    from datetime import date
    sent, updates = run_boost([boost_row("2026-09-20")], None, [1], NOW.replace(day=27))
    assert sent == [] and updates == [(False, date(2026, 9, 20))]


def test_fan_out_boost_retries_when_nobody_reachable():
    sent, updates = run_boost([boost_row("2026-09-27")], None, [1], NOW.replace(day=27),
                              reachable=False)
    assert len(sent) == 1 and updates == []


def test_fan_out_boost_marks_plain_days_without_sending():
    from datetime import date
    sent, updates = run_boost([boost_row("2026-09-27", units=1.0, fear_add=0.0)], None, [1],
                              NOW.replace(day=27))
    assert sent == [] and updates == [(False, date(2026, 9, 27))]
