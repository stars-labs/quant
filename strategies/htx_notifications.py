"""Private HTX execution reminders delivered by the existing Telegram dispatcher."""

from datetime import datetime, timedelta, timezone
from html import escape

from htx_order_store import OrderStore
from htx_fill_costs import fee_details, quantity


def format_fills(rows, trend, dca):
    lines = ['<b>HTX 实盘成交</b>（金额已计手续费）']
    for cid, kind, asset, side, qty, cash, finished, amount, cost, taker, basic in rows:
        label = '趋势' if kind == 'trend' else '定投'
        action = '买入' if side == 'buy' else '卖出'
        movement = '支出' if side == 'buy' else '净回款'
        stamp = finished.astimezone(timezone.utc).strftime('%m-%d %H:%M UTC')
        lines.append(f'{stamp} · {label} {action} {quantity(qty)} '
                     f'{escape(asset)} · {movement} {abs(float(cash)):.4f} USDT')
        if amount is None or cost is None:
            lines.append('手续费明细待核对')
            continue
        base_fee,quote_fee,equivalent,rate = fee_details(side,qty,cash,amount,cost)
        parts = ([f'{quantity(base_fee)} {escape(asset)}'] if base_fee else [])
        if quote_fee:
            parts.append(f'{quantity(quote_fee)} USDT')
        lines.append('手续费：' + (' + '.join(parts) or '0') +
                     f'（成交均价折算 {equivalent:.4f} USDT，实扣 {rate:.3%}）')
        if taker is not None and basic is not None:
            lines.append(f'下单查询：折后 {float(taker):.3%} / 基础 {float(basic):.3%}' +
                         ('；实扣高于折后报价' if rate>float(taker)+1e-8 else ''))
    lines.append(f'当前可用预算：趋势 {trend:.2f} USDT / 本月定投 {dca:.2f} USDT')
    return '\n'.join(lines)


def notify_htx(conn, state, send, chat_id, now=None):
    """Acknowledge only successful sends; never acquire the executor's trading lock."""
    if not chat_id:
        return
    now = now or datetime.now(timezone.utc)
    month = now.date().replace(day=1)
    with conn.cursor() as cur:
        cur.execute("SELECT checked_at,healthy,detail FROM quant.executor_status WHERE venue='HTX'")
        status = cur.fetchone()
    if not status:
        return  # No configured live executor: no private account reminders.
    checked, healthy, detail = status
    healthy = healthy and now - checked <= timedelta(minutes=5)
    previous = state.get('htx_healthy')
    if previous != healthy:
        if healthy and previous is None:
            state['htx_healthy'] = True
        else:
            text = ('✅ HTX 实盘执行检查恢复正常。' if healthy else
                    '⚠️ HTX 实盘执行异常，需检查；新订单可能暂停。\n原因：' +
                    escape(detail if now - checked <= timedelta(minutes=5) else '执行器心跳超过 5 分钟'))
            if send(int(chat_id), text):
                state['htx_healthy'] = healthy
    store = OrderStore.__new__(OrderStore)
    store.conn = conn
    with conn.cursor() as cur:
        cur.execute("""SELECT client_id,kind,asset,side,asset_delta,cash_delta,finished_at,
            filled_amount,filled_cost,quoted_taker_rate,quoted_basic_rate
            FROM quant.executor_orders WHERE venue='HTX' AND environment='live'
            AND status='done' AND notified_at IS NULL
            ORDER BY finished_at,client_id LIMIT 20""")
        rows = cur.fetchall()
    fills = [r for r in rows if r[4] or r[5]]
    if rows and (not fills or send(int(chat_id), format_fills(
            fills, store.budget('trend', month), store.budget('dca', month)))):
        with conn.cursor() as cur:
            cur.execute('UPDATE quant.executor_orders SET notified_at=now() WHERE client_id=ANY(%s)',
                        ([r[0] for r in rows],))
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM quant.executor_funding WHERE venue='HTX' "
                    "AND environment='live' AND month=%s", (month,))
        funded = cur.fetchone() is not None
    if not funded and state.get('htx_funding_reminder') != month.isoformat():
        if send(int(chat_id), f'📅 HTX {month:%Y-%m} 月度入金提醒\n'
                '本月 200 USDT 尚未确认（趋势 100 / BTC 定投 100）。'
                '到账并登记预算后才能使用新资金；趋势卖出回款仍可复用。'):
            state['htx_funding_reminder'] = month.isoformat()
