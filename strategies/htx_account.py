"""Owner-private Telegram display; never accesses exchange keys or execution tables."""
import os
from datetime import datetime, timezone
from html import escape

from htx_notifications import format_fills, report_health, runner_reports, timestamp

MENU = {'keyboard': [[{'text': '/live'}, {'text': '/trades'}]], 'resize_keyboard': True}
COMMANDS = [{'command': 'live', 'description': 'HTX live account report'},
            {'command': 'trades', 'description': 'Recent HTX live fills'},
            {'command': 'me', 'description': 'My HTX live account'}]


def is_owner(msg, operator):
    chat = msg.get('chat') or {}
    return bool(operator and chat.get('type') == 'private'
                and str(chat.get('id')) == str(operator)
                and (msg.get('from') or {}).get('id') == chat.get('id'))


def latest_report(conn, operator=None):
    rows = runner_reports(conn, operator or os.environ.get('TELEGRAM_CHAT_ID'))
    return next((r for r in rows if r[3]), None)


def account_text(conn, now=None, operator=None):
    now = now or datetime.now(timezone.utc)
    row = latest_report(conn, operator)
    if not row:
        return '<b>HTX live account</b>\nNo connected local runner report yet.'
    _, label, _, report = row
    health = report_health(row, now)
    lines = ['<b>HTX live account</b> · ' + escape(label), 'Reported status: ' + escape(health)]
    if health in ('stale', 'missing'):
        lines.append('Reporting is unavailable or over 5 minutes old. Local execution may still be running.')
    lines += [f"Last observed: {timestamp(report['observed_at']):%m-%d %H:%M UTC}",
              f"Confirmed funding: {report['funded_usdt']:.2f} USDT",
              f"Tracked cash: {report['cash_usdt']:.2f} USDT",
              f"Tracked equity: {report['equity_usdt']:.2f} USDT",
              f"Estimated net PnL: {report['equity_usdt']-report['funded_usdt']:+.2f} USDT",
              f"Actual fees: {report['fees_usdt']:.4f} USDT equivalent",
              f"Available: trend {report['trend_available_usdt']:.2f} / monthly BTC DCA {report['dca_available_usdt']:.2f} USDT",
              '\n<b>Reported positions</b>']
    for position in report['positions']:
        value = position['quantity'] * position['price_usdt']
        lines.append(f"{escape(position['strategy'])} · {escape(position['asset'])} "
                     f"{position['quantity']:.10g} · estimated value {value:.2f} USDT")
    if not report['positions']:
        lines.append('No reported positions.')
    lines.append('User-reported local journal; hourly research close valuation. Unconfirmed deposits are excluded; future sell fees are excluded.')
    return '\n'.join(lines)


def trades_text(conn, now=None, operator=None):
    row = latest_report(conn, operator)
    if not row or not row[3]['fills']:
        return '<b>HTX live fills</b>\nNo reported fills.'
    report = row[3]
    text = format_fills(sorted(report['fills'], key=lambda f: (f['finished_at'], f['client_id']),
                              reverse=True)[:10], report['trend_available_usdt'], report['dca_available_usdt'])
    if report_health(row, now or datetime.now(timezone.utc)) in ('stale', 'missing'):
        text += '\nHistorical report: reporting is over 5 minutes old; local execution may still be running.'
    return text


def handle_account(conn, msg, command, send, operator):
    owner = is_owner(msg, operator)
    if command not in ('/live', '/trades') and not (owner and command in ('/me', '/start')):
        return False
    chat_id = (msg.get('chat') or {}).get('id')
    if not owner:
        send(chat_id, 'Live account queries are available only in the account owner’s private chat.')
        return True
    text = trades_text(conn, operator=operator) if command == '/trades' else account_text(conn, operator=operator)
    send(chat_id, text, MENU)
    return True
