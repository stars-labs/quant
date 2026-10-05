"""Read-only, owner-private Telegram view of the real HTX execution journal."""

import math
from datetime import datetime, timedelta, timezone
from html import escape

from htx_notifications import format_fills
from htx_order_store import OrderStore
from htx_fill_costs import fee_details, quantity


MENU = {'keyboard': [[{'text': '/live'}, {'text': '/trades'}]],
        'resize_keyboard': True}
COMMANDS = [{'command': 'live', 'description': 'HTX 实盘持仓、现金与盈亏'},
            {'command': 'trades', 'description': 'HTX 最近真实成交'},
            {'command': 'me', 'description': '我的 HTX 实盘账户'}]


def is_owner(msg, operator):
    chat = msg.get('chat') or {}
    return bool(operator and chat.get('type') == 'private'
                and str(chat.get('id')) == str(operator)
                and (msg.get('from') or {}).get('id') == chat.get('id'))


def readonly_store(conn):
    store = OrderStore.__new__(OrderStore)
    store.conn = conn
    return store


def account_text(conn, now=None):
    now = now or datetime.now(timezone.utc)
    month = now.date().replace(day=1)
    store = readonly_store(conn)
    holdings = sorted(store.holdings(),key=lambda h:(h.kind!='trend',h.asset))
    cash = store.expected_cash()
    with conn.cursor() as cur:
        cur.execute("SELECT checked_at,healthy,detail FROM quant.executor_status WHERE venue='HTX'")
        status = cur.fetchone()
        cur.execute("SELECT asset,last_close,last_ts,updated_at FROM quant.strategy_assets "
                    "WHERE strategy='donchian_1h'")
        prices = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute("SELECT coalesce(sum(trend_usdt+dca_usdt),0) FROM quant.executor_funding "
                    "WHERE venue='HTX' AND environment='live'")
        funding = float(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM quant.executor_orders WHERE venue='HTX' "
                    "AND environment='live' AND status='pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT id,asset FROM quant.strategy_signals WHERE strategy='donchian_1h' "
                    "AND exit_ts IS NULL ORDER BY asset")
        targets = {f'HTX-signal-{r[0]}':r[1] for r in cur.fetchall()}
        cur.execute("SELECT side,asset_delta,cash_delta,filled_amount,filled_cost "
                    "FROM quant.executor_orders WHERE venue='HTX' AND environment='live' "
                    "AND status='done' AND (asset_delta<>0 OR cash_delta<>0)")
        fills = cur.fetchall()
    lines = ['<b>HTX 实盘账户</b>']
    if status:
        checked, healthy, detail = status
        fresh = now - checked <= timedelta(minutes=5)
        label = '检查正常' if healthy and fresh else '需检查'
        stamp = checked.astimezone(timezone.utc)
        lines.append(f'执行状态：{label} · 最近检查 {stamp:%m-%d %H:%M UTC}')
        if not fresh or not healthy:
            lines.append('原因：' + escape(detail if fresh else '心跳超过 5 分钟'))
    else:
        lines.append('执行状态：暂无检查记录')
    lines += [f'待确认订单：{pending} 笔', f'累计确认投入：{funding:.2f} USDT',
              f'账本现金：{cash:.2f} USDT',
              f'可用预算：趋势 {store.budget("trend", month):.2f} / '
              f'本月定投 {store.budget("dca", month):.2f} USDT', '\n<b>实际持仓</b>']
    value, complete, stamps = 0.0, True, []
    for h in holdings:
        if h.qty <= 0:
            continue
        label = '趋势' if h.kind == 'trend' else 'BTC 定投'
        base = f'{label} · {escape(h.asset)} {quantity(h.qty)}'
        price = prices.get(h.asset)
        if (price and price[0] is not None and math.isfinite(float(price[0]))
                and float(price[0]) > 0 and price[1] is not None and price[2] is not None
                and max(price[1:]) <= now
                and now - min(price[1:]) <= timedelta(hours=3)):
            market_value = h.qty * float(price[0])
            unrealized = market_value - h.qty * h.cost / h.bought
            value += market_value
            stamps.append(price[1].astimezone(timezone.utc))
            lines.append(base + f' · 估值 {market_value:.2f} · 浮盈亏 {unrealized:+.2f} USDT')
        else:
            complete = False
            lines.append(base + ' · 行情缺失或过期，暂不估值')
    if not any(h.qty > 0 for h in holdings):
        lines.append('暂无持仓')
    held = {h.key for h in holdings if h.kind=='trend' and h.qty>0}
    waiting = sorted(asset for key,asset in targets.items() if key not in held)
    if waiting:
        lines.append('当前有信号、尚未建仓：' + ' / '.join(escape(a) for a in waiting))
        lines.append('按可用趋势预算、单笔 20 USDT 上限及交易所最小金额执行。')
    verified = [r for r in fills if r[3] is not None and r[4] is not None]
    total_fee = sum(fee_details(*r)[2] for r in verified)
    lines.append(f'累计实扣手续费（按成交均价折算）：{total_fee:.4f} USDT')
    if len(verified)<len(fills):
        lines.append(f'另有 {len(fills)-len(verified)} 笔手续费明细待核对，未计入上项。')
    realized = sum(h.proceeds - (h.bought-h.qty)*h.cost/h.bought
                   for h in holdings if h.bought > 0)
    lines.append(f'\n已实现盈亏（含手续费）：{realized:+.2f} USDT')
    if complete:
        equity = cash + value
        lines += [f'估算总资产：{equity:.2f} USDT',
                  f'累计总盈亏：{equity-funding:+.2f} USDT']
    else:
        lines.append('行情不完整，暂不计算总资产与总盈亏。')
    if stamps:
        lines.append(f'估值行情：小时收盘价，最早截至 {min(stamps):%m-%d %H:%M UTC}')
    lines.append('持仓与现金来自实盘成交账本；未确认入金不计入，估值未扣未来卖出费用。')
    return '\n'.join(lines)


def trades_text(conn, now=None):
    now = now or datetime.now(timezone.utc)
    store = readonly_store(conn)
    with conn.cursor() as cur:
        cur.execute("""SELECT client_id,kind,asset,side,asset_delta,cash_delta,finished_at,
            filled_amount,filled_cost,quoted_taker_rate,quoted_basic_rate
            FROM quant.executor_orders WHERE venue='HTX' AND environment='live'
            AND status='done' AND (asset_delta<>0 OR cash_delta<>0)
            ORDER BY finished_at DESC,client_id LIMIT 10""")
        rows = cur.fetchall()
    if not rows:
        return '<b>HTX 最近真实成交</b>\n暂无成交。'
    month = now.date().replace(day=1)
    return format_fills(rows, store.budget('trend', month), store.budget('dca', month)).replace(
        '<b>HTX 实盘成交</b>', '<b>HTX 最近 10 笔真实成交</b>', 1)


def handle_account(conn, msg, command, send, operator):
    owner = is_owner(msg, operator)
    if command not in ('/live', '/trades') and not (owner and command in ('/me', '/start')):
        return False
    chat_id = (msg.get('chat') or {}).get('id')
    if not owner:
        send(chat_id, '实盘账户查询仅在账户所有者的私人聊天中可用。')
        return True
    text = trades_text(conn) if command == '/trades' else account_text(conn)
    send(chat_id, text, MENU)
    return True
