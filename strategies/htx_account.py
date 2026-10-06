"""Owner-private Telegram display; never accesses exchange keys or execution tables."""
import os
from datetime import datetime, timezone
from html import escape

from htx_notifications import format_fills, report_health, runner_reports, timestamp

MENU = {'keyboard': [[{'text': '/live'}, {'text': '/trades'}],
    [{'text':'/livealerts on'},{'text':'/livealerts off'}]], 'resize_keyboard': True}
COMMANDS = [{'command': 'live', 'description': 'HTX live account report'},
            {'command': 'trades', 'description': 'Recent HTX live fills'},
            {'command': 'livealerts', 'description': 'Private runner alerts on/off'},
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
    for position in report['positions'][:14]:
        value = position['quantity'] * position['price_usdt']
        lines.append(f"{escape(position['strategy'])} · {escape(position['asset'])} "
                     f"{position['quantity']:.10g} · estimated value {value:.2f} USDT")
    if len(report['positions'])>14:
        lines.append(f"{len(report['positions'])-14} more positions: review your private account page.")
    if not report['positions']:
        lines.append('No reported positions.')
    decisions = report.get('decisions') or []
    if decisions:
        reasons = {'pending_reconciliation':'Awaiting existing order confirmation',
            'exit_submitted':'Exit submitted','entry_submitted':'Buy submitted',
            'below_exchange_minimum':'Below exchange minimum','no_entry_signal':'No entry signal',
            'target_already_processed':'Signal already processed',
            'confirmed_budget_unavailable':'No confirmed budget','entries_disabled':'Entries disabled',
            'no_dca_signal':'No DCA instruction','today_already_processed':'Today’s DCA processed',
            'reconciliation_failed':'Reconciliation failed','signal_feed_failed':'Signal feed unavailable',
            'execution_failed':'Execution checks failed'}
        lines.append('\n<b>Latest execution decisions</b>')
        for decision in decisions[:14]:
            lines.append(escape(decision.get('asset') or 'Account')+' · '+reasons.get(decision['reason'],'Check owner diagnostics'))
    attribution = report.get('attribution') or []
    if attribution:
        lines.append('\n<b>Net PnL by strategy</b>')
        for strategy in ('trend','dca'):
            rows = [item for item in attribution if item['strategy']==strategy]
            if rows:
                realized = sum(item['realized_pnl_usdt'] for item in rows)
                unrealized = sum(item['unrealized_pnl_usdt'] for item in rows)
                lines.append(f'{strategy}: realized {realized:+.2f}, unrealized {unrealized:+.2f} USDT (fees included)')
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


def handle_account(conn, msg, command, send, operator, argument=""):
    owner = is_owner(msg, operator)
    if command not in ('/live', '/trades','/livealerts') and not (owner and command in ('/me', '/start')):
        return False
    chat_id = (msg.get('chat') or {}).get('id')
    private_sender = ((msg.get('chat') or {}).get('type')=='private'
        and isinstance(chat_id,int) and (msg.get('from') or {}).get('id')==chat_id)
    if not private_sender:
        send(chat_id, 'Live account queries are available only in the account owner’s private chat.')
        return True
    if command=='/livealerts':
        if argument.strip() not in ('on','off'):
            send(chat_id,'Use /livealerts on or /livealerts off. These settings only control report notifications.')
            return True
        with conn.cursor() as cur:
            cur.execute('SELECT quant.set_runner_alerts(%s,%s)',(chat_id,argument.strip()=='on'))
            linked = cur.fetchone()[0]
        send(chat_id,('Private runner alerts '+argument.strip()+'.') if linked else
            'Bind your Telegram account and connect a live runner report before enabling alerts.')
        return True
    text = trades_text(conn, operator=str(chat_id)) if command == '/trades' else account_text(conn, operator=str(chat_id))
    send(chat_id, text, MENU)
    return True
