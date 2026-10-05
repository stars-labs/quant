"""Private routing and real-journal valuation, including shared BTC and stale marks."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'strategies'))
import htx_account as ha
from htx_order_store import Holding
import alert_dispatcher as ad

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
OWNER = {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 123}}


class DB:
    def __init__(self):
        self.price = ('BTC', 110, NOW, NOW)
        self.rows = [('one', 'trend', 'BTC', 'buy', .2, -20, NOW, .2004, 20, .0015, .002)]
        self.status = (NOW, True, 'ok')
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=None):
        if 'executor_status' in sql: self.result = [self.status] if self.status else []
        elif 'strategy_assets' in sql: self.result = [self.price] if self.price else []
        elif 'strategy_signals' in sql: self.result = [(1,'BTC'), (2,'SOL')]
        elif 'SELECT side,asset_delta' in sql: self.result = [('buy',.2,-20,.2004,20)]
        elif 'executor_funding' in sql: self.result = [(200,)]
        elif 'count(*)' in sql: self.result = [(0,)]
        elif 'executor_orders' in sql: self.result = self.rows
        else: raise AssertionError(sql)
    def fetchone(self): return self.result[0] if self.result else None
    def fetchall(self): return self.result


def text(db):
    # Trend bought .4BTC for40, sold half for22 -> +2 realized; DCA owns .1 for10.
    holdings = [Holding('HTX-signal-1', 'trend', 'BTC', .2, .4, 40, 22, NOW),
                Holding('dca', 'dca', 'BTC', .1, .1, 10, 0, NOW)]
    with patch.object(ha.OrderStore, 'holdings', return_value=holdings), \
         patch.object(ha.OrderStore, 'expected_cash', return_value=172), \
         patch.object(ha.OrderStore, 'budget', return_value=90):
        return ha.account_text(db, NOW)


def test_actual_net_account_and_shared_btc():
    result = text(DB())
    assert '趋势 · BTC 0.2' in result and 'BTC 定投 · BTC 0.1' in result
    assert '已实现盈亏（含手续费）：+2.00' in result
    assert '估算总资产：205.00' in result and '累计总盈亏：+5.00' in result
    assert '账本现金：172.00' in result and '小时收盘价' in result
    assert '累计实扣手续费' in result and '当前有信号、尚未建仓：SOL' in result
    assert '尚未建仓：BTC' not in result


def test_stale_missing_nan_future_marks_hide_total():
    db = DB()
    for mark in [None, ('BTC', 110, NOW-timedelta(hours=4), NOW),
                 ('BTC', float('nan'), NOW, NOW),
                 ('BTC', 110, NOW+timedelta(hours=1), NOW)]:
        db.price = mark
        result = text(db)
        assert '暂不计算总资产' in result and '估算总资产：' not in result


def test_status_stale_and_missing():
    db = DB()
    db.status = (NOW-timedelta(minutes=6), True, 'ok')
    assert '心跳超过 5 分钟' in text(db)
    db.status = None
    assert '暂无检查记录' in text(db)


def test_unauthorized_chat_and_group_never_read_account():
    for msg in [{'chat': {'id': 456, 'type': 'private'}, 'from': {'id': 456}},
                {'chat': {'id': 123, 'type': 'group'}, 'from': {'id': 123}},
                {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 456}},
                {'chat': {'id': 123, 'type': 'private'}}]:
        replies = []
        assert ha.handle_account(None, msg, '/live', lambda *args: replies.append(args), '123')
        assert '仅在账户所有者' in replies[0][1]
        assert not ha.handle_account(None, msg, '/me', lambda *args: None, '123')
    assert not ha.is_owner(OWNER, None)


def test_owner_me_start_and_commands_show_real_account():
    for cmd in ('/start', '/me', '/live', '/trades'):
        replies = []
        with patch.object(ha, 'account_text', return_value='live'), \
             patch.object(ha, 'trades_text', return_value='trades'):
            assert ha.handle_account(None, OWNER, cmd, lambda *args: replies.append(args), '123')
        assert replies == [(123, 'trades' if cmd=='/trades' else 'live', ha.MENU)]


def test_recent_real_fills_and_empty():
    db = DB()
    with patch.object(ha.OrderStore, 'budget', return_value=80):
        assert '最近 10 笔真实成交' in ha.trades_text(db, NOW)
        db.rows = []
        assert '暂无成交' in ha.trades_text(db, NOW)


def test_owner_scoped_menu_and_failed_initial_summary_retry():
    state, calls = {}, []
    with patch.dict(ad.os.environ, {'TELEGRAM_CHAT_ID': '123'}), \
         patch.object(ad, 'tg', side_effect=lambda *args, **kw: calls.append(kw)), \
         patch.object(ad, 'account_text', return_value='real account'), \
         patch.object(ad, 'send', return_value=False):
        ad.ensure_operator_menu(None, state)
        assert 'htx_menu_version' not in state
    assert calls[0]['scope'] == {'type': 'chat', 'chat_id': 123}
    with patch.dict(ad.os.environ, {'TELEGRAM_CHAT_ID': '123'}), \
         patch.object(ad, 'tg', return_value=True), \
         patch.object(ad, 'account_text', return_value='real account'), \
         patch.object(ad, 'send', return_value=True) as send:
        ad.ensure_operator_menu(None, state)
        ad.ensure_operator_menu(None, state)
        assert send.call_count==1
        assert send.call_args.args==(123,'real account',ha.MENU)


def test_poll_routes_owner_me_without_public_follow_query():
    msg = dict(OWNER, text='/me')
    state = {'tg_offset': 0}
    with patch.dict(ad.os.environ, {'TELEGRAM_CHAT_ID': '123'}), \
         patch.object(ad, 'tg', return_value=[{'update_id': 1, 'message': msg}]), \
         patch.object(ha, 'account_text', return_value='live account'), \
         patch.object(ad, 'send', return_value=True) as send, \
         patch.object(ad, 'handle_me', side_effect=AssertionError):
        ad.poll_updates(None, state)
        assert send.call_args.args==(123,'live account',ha.MENU)
        assert state['tg_offset']==1
