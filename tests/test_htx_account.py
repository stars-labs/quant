"""Private owner routing and read-only uploaded account reports."""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'strategies'))
import htx_account as ha

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
OWNER = {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 123}}


def report():
    return {'observed_at': NOW.isoformat(), 'status': 'healthy', 'funded_usdt': 200.,
            'cash_usdt': 172., 'equity_usdt': 205., 'fees_usdt': .04,
            'trend_available_usdt': 90., 'dca_available_usdt': 90.,
            'positions': [{'strategy': 'trend', 'asset': 'BTC', 'quantity': .2,
                           'price_usdt': 110.}],
            'fills': [{'client_id': 'one', 'strategy': 'trend', 'asset': 'BTC',
                       'side': 'buy', 'quantity': .2, 'quote_usdt': 20.,
                       'fee_usdt': .04, 'fee_rate': .002, 'finished_at': NOW.isoformat()}]}


class DB:
    def __init__(self):
        self.rows = [('connection', '<private>', NOW, report())]
        self.calls = []
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params):
        assert sql == 'SELECT id,label,received_at,report FROM quant.private_runner_reports(%s)'
        self.calls.append(params)
    def fetchall(self): return self.rows


def test_account_report_net_values_and_escaping():
    db = DB()
    result = ha.account_text(db, NOW, '123')
    assert db.calls == [(123,)]
    assert 'Tracked cash: 172.00' in result and 'Tracked equity: 205.00' in result
    assert 'Estimated net PnL: +5.00' in result and 'Actual fees: 0.0400' in result
    assert '&lt;private&gt;' in result and 'trend · BTC 0.2' in result
    assert 'User-reported local journal' in result


def test_stale_and_missing_do_not_claim_executor_stopped():
    db = DB()
    text = ha.account_text(db, NOW+timedelta(minutes=6), '123')
    assert 'Local execution may still be running' in text
    assert 'Reported status: stale' in text
    db.rows = []
    assert 'No connected local runner' in ha.account_text(db, NOW, '123')


def test_no_operator_never_queries_private_db():
    with patch.dict(os.environ, {}, clear=True):
        assert 'No connected local runner' in ha.account_text(None, NOW)


def test_unauthorized_chat_and_group_never_read_account():
    for msg in [{'chat': {'id': 123, 'type': 'group'}, 'from': {'id': 123}},
                {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 456}},
                {'chat': {'id': 123, 'type': 'private'}}]:
        replies = []
        assert ha.handle_account(None, msg, '/live', lambda *args: replies.append(args), '123')
        assert 'only in the account owner' in replies[0][1]
        assert not ha.handle_account(None, msg, '/me', lambda *args: None, '123')
    assert not ha.is_owner(OWNER, None)


def test_owner_commands_pass_explicit_owner_to_query():
    for cmd in ('/start', '/me', '/live', '/trades'):
        replies = []
        db = DB()
        assert ha.handle_account(db, OWNER, cmd, lambda *args: replies.append(args), '123')
        assert db.calls == [(123,)] and replies[0][0] == 123 and replies[0][2] == ha.MENU


def test_recent_fills_and_empty():
    db = DB()
    text = ha.trades_text(db, NOW, '123')
    assert 'gross 20.0000 USDT' in text and '(0.200%)' in text
    db.rows[0][3]['fills'] = []
    assert 'No reported fills' in ha.trades_text(db, NOW, '123')


def test_dispatcher_owner_menu_initial_summary_retries():
    import alert_dispatcher as ad
    state, calls = {}, []
    with patch.dict(ad.os.environ, {'TELEGRAM_CHAT_ID': '123'}), \
         patch.object(ad, 'tg', side_effect=lambda *args, **kw: calls.append(kw)), \
         patch.object(ad, 'account_text', return_value='local report'), \
         patch.object(ad, 'send', return_value=False):
        ad.ensure_operator_menu(None, state)
        assert 'htx_menu_version' not in state
    assert calls[0]['scope'] == {'type': 'chat', 'chat_id': 123}
    with patch.dict(ad.os.environ, {'TELEGRAM_CHAT_ID': '123'}), \
         patch.object(ad, 'tg', return_value=True), \
         patch.object(ad, 'account_text', return_value='local report'), \
         patch.object(ad, 'send', return_value=True) as send:
        ad.ensure_operator_menu(None, state)
        ad.ensure_operator_menu(None, state)
        assert send.call_count == 1
        assert send.call_args.args == (123, 'local report', ha.MENU)


def test_dispatcher_owner_me_does_not_read_public_follow_record():
    import alert_dispatcher as ad
    state = {'tg_offset': 0}
    with patch.dict(ad.os.environ, {'TELEGRAM_CHAT_ID': '123'}), \
         patch.object(ad, 'tg', return_value=[{'update_id': 1, 'message': dict(OWNER, text='/me')}]), \
         patch.object(ha, 'account_text', return_value='local report'), \
         patch.object(ad, 'send', return_value=True) as send, \
         patch.object(ad, 'handle_me', side_effect=AssertionError):
        ad.poll_updates(None, state)
        assert send.call_args.args == (123, 'local report', ha.MENU)
        assert state['tg_offset'] == 1


def test_account_decisions_show_safe_owner_explanations():
    data = report()
    data['decisions'] = [{'strategy':'trend','asset':'BTC','reason':'confirmed_budget_unavailable'}]
    with patch.object(ha, 'latest_report', return_value=('id','Mine',NOW,data)):
        text = ha.account_text(None, now=NOW, operator='123')
    assert 'No confirmed budget' in text
    assert 'Latest execution decisions' in text


def test_bound_user_queries_only_own_chat_and_keeps_public_me():
    msg = {'chat':{'id':456,'type':'private'},'from':{'id':456}}
    db, replies = DB(), []
    assert ha.handle_account(db,msg,'/live',lambda *args:replies.append(args),'123')
    assert db.calls==[(456,)]
    assert replies[0][0]==456
    assert not ha.handle_account(db,msg,'/me',lambda *args:None,'123')


def test_unbound_private_user_receives_no_report():
    msg = {'chat':{'id':456,'type':'private'},'from':{'id':456}}
    db, replies = DB(), []
    db.rows = []
    assert ha.handle_account(db,msg,'/live',lambda *args:replies.append(args),'123')
    assert db.calls==[(456,)]
    assert 'No connected local runner report' in replies[0][1]
    assert 'Tracked cash' not in replies[0][1]
