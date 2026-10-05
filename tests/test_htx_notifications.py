"""Private delivery, retry, restart acknowledgement and status transitions."""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'strategies'))
import htx_notifications as hn

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)

class DB:
    def __init__(self):
        self.status = (NOW, True, 'ok')
        self.rows = [('one', 'trend', 'BTC', 'buy', .001, -20, NOW)]
        self.funded = True
        self.marked = []
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=None):
        if 'executor_status' in sql: self.result = [self.status] if self.status else []
        elif 'SET notified_at' in sql:
            self.marked += params[0]
            self.rows = [r for r in self.rows if r[0] not in params[0]]
        elif 'executor_orders' in sql: self.result = self.rows
        elif 'executor_funding' in sql: self.result = [(1,)] if self.funded else []
        else: raise AssertionError(sql)
    def fetchone(self): return self.result[0] if self.result else None
    def fetchall(self): return self.result

def run(db, state, ok=True, now=NOW):
    messages = []
    def send(chat, text):
        assert chat == 123
        messages.append(text)
        return ok
    with patch.object(hn.OrderStore, 'budget', return_value=80):
        hn.notify_htx(db, state, send, '123', now)
    return messages

def test_delivery_retry_and_restart():
    db, state = DB(), {}
    assert len(run(db, state, False)) == 1
    assert db.marked == []
    text = run(db, state)[0]
    assert 'HTX 实盘成交' in text and '20.0000 USDT' in text and '80.00' in text
    assert db.marked == ['one']
    assert run(db, {}) == []

def test_status_failure_recovery_and_retry():
    db, state = DB(), {}
    db.rows = []
    db.status = (NOW, False, '<problem>')
    assert '&lt;problem&gt;' in run(db, state, False)[0]
    assert 'htx_healthy' not in state
    assert len(run(db, state)) == 1
    assert run(db, state) == []
    db.status = (NOW, True, 'ok')
    assert '恢复正常' in run(db, state)[0]
    assert run(db, state) == []

def test_stale_heartbeat():
    db, state = DB(), {'htx_healthy': True}
    db.rows = []
    assert '心跳' in run(db, state, now=NOW+timedelta(minutes=6))[0]

def test_monthly_reminder_retries_and_once():
    db, state = DB(), {}
    db.rows, db.funded = [], False
    assert '200 USDT' in run(db, state, False)[0]
    assert 'htx_funding_reminder' not in state
    assert len(run(db, state)) == 1
    assert run(db, state) == []
    assert '2026-11' in run(db, state, now=NOW.replace(month=11))[-1]

def test_no_live_or_operator_no_send():
    db = DB()
    db.status = None
    assert run(db, {}) == []
    hn.notify_htx(db, {}, lambda *args: (_ for _ in ()).throw(AssertionError()), None)

def test_sale_and_zero_fill():
    db = DB()
    db.rows = [('sale', 'trend', 'ETH', 'sell', -.1, 25.5, NOW),
               ('zero', 'dca', 'BTC', 'buy', 0, 0, NOW)]
    text = run(db, {})[0]
    assert '卖出' in text and '净回款 25.5000' in text and '定投' not in text.split('当前')[0]
    assert db.marked == ['sale', 'zero']
