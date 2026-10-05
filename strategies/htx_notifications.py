"""Read-only notifications from owner-uploaded HTX runner reports."""
from datetime import datetime, timedelta, timezone
from html import escape


def runner_reports(conn, chat_id):
    if not chat_id:
        return []
    with conn.cursor() as cur:
        cur.execute('SELECT id,label,received_at,report FROM quant.operator_runner_reports(%s)',
                    (int(chat_id),))
        return cur.fetchall()


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def report_health(row, now):
    received, report = row[2], row[3]
    if not received or not report:
        return 'missing'
    observed = timestamp(report['observed_at'])
    if min(received, observed) < now - timedelta(minutes=5):
        return 'stale'
    return report['status']


def format_fills(rows, trend, dca):
    lines = ['<b>HTX live fills</b>']
    for fill in rows:
        stamp = timestamp(fill['finished_at']).strftime('%m-%d %H:%M UTC')
        lines.append(f"{stamp} · {escape(fill['strategy'])} {escape(fill['side'])} "
                     f"{float(fill['quantity']):.10g} {escape(fill['asset'])} · "
                     f"gross {float(fill['quote_usdt']):.4f} USDT")
        lines.append(f"Actual fee: {float(fill['fee_usdt']):.4f} USDT equivalent "
                     f"({float(fill['fee_rate']):.3%})")
    lines.append(f'Available: trend {trend:.2f} / monthly BTC DCA {dca:.2f} USDT')
    return '\n'.join(lines)


def notify_htx(conn, state, send, chat_id, now=None):
    """Seed historical fills once; advance durable delivery state only after success."""
    if not chat_id:
        return
    now = now or datetime.now(timezone.utc)
    connections = state.setdefault('runner_notifications', {})
    for row in runner_reports(conn, chat_id):
        identity, label, _, report = row
        if not report:
            continue
        key = str(identity)
        cursor = connections.get(key)
        fills = sorted(report['fills'], key=lambda f: (f['finished_at'], f['client_id']))
        health = report_health(row, now)
        if cursor is None:
            # Imported historical fills must not be announced as newly executed trades.
            cursor = {'seen': [f['client_id'] for f in fills], 'health': 'healthy'}
            connections[key] = cursor
        if cursor['health'] != health:
            if health == 'healthy':
                text = '✅ HTX runner reporting recovered.'
            elif health in ('stale', 'missing'):
                text = ('⚠️ HTX runner reports are unavailable or over 5 minutes old. '
                        'This does not establish whether local execution has stopped.')
            else:
                text = ('⚠️ HTX local runner reports status: ' + escape(health) +
                        '. Check your local runner before taking action.')
            if send(int(chat_id), text + '\n' + escape(label)):
                cursor['health'] = health
        unseen = [f for f in fills if f['client_id'] not in cursor['seen']]
        if unseen and send(int(chat_id), escape(label) + '\n' + format_fills(
                unseen, report['trend_available_usdt'], report['dca_available_usdt'])):
            cursor['seen'].extend(f['client_id'] for f in unseen)
        # Reports contain the most recent 50 fills. Keep retry IDs and this window only.
        current = {f['client_id'] for f in fills}
        cursor['seen'] = [cid for cid in cursor['seen'] if cid in current]
