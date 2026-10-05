"""Report-based notifications seed history, retry failures and persist delivery state."""
import json
import sys
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_htx_account import DB, NOW
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'strategies'))
import htx_notifications as hn


def run(db, state, ok=True, now=NOW):
    messages = []
    def send(chat, text):
        assert chat == 123
        messages.append(text)
        return ok
    hn.notify_htx(db, state, send, '123', now)
    return messages


def test_history_seed_and_new_fill_retry_and_restart():
    db, state = DB(), {}
    assert run(db, state) == []
    fill = dict(db.rows[0][3]['fills'][0], client_id='two')
    db.rows[0][3]['fills'].append(fill)
    assert 'HTX live fills' in run(db, state, False)[0]
    assert state['runner_notifications']['connection']['seen'] == ['one']
    assert len(run(db, state)) == 1
    assert state['runner_notifications']['connection']['seen'] == ['one', 'two']
    assert run(db, json.loads(json.dumps(state))) == []


def test_status_failure_retry_and_recovery():
    db, state = DB(), {}
    db.rows[0][3]['status'] = 'pending'
    assert 'pending' in run(db, state, False)[0]
    assert state['runner_notifications']['connection']['health'] == 'healthy'
    assert len(run(db, state)) == 1
    assert run(db, state) == []
    db.rows[0][3]['status'] = 'healthy'
    assert 'reporting recovered' in run(db, state)[0]
    assert run(db, state) == []


def test_stale_reporting_never_claims_execution_stopped():
    db, state = DB(), {}
    run(db, state)
    text = run(db, state, now=NOW+timedelta(minutes=6))[0]
    assert 'does not establish whether local execution has stopped' in text
    assert 'over 5 minutes' in text


def test_new_connection_isolated_and_unbound_operator_no_read():
    db, state = DB(), {}
    run(db, state)
    db.rows[0] = ('other', '<new>', NOW, db.rows[0][3])
    assert run(db, state) == []
    assert set(state['runner_notifications']) == {'connection', 'other'}
    hn.notify_htx(None, {}, lambda *args: (_ for _ in ()).throw(AssertionError()), None)


def test_sale_gross_and_fee_not_subtracted_twice():
    db, state = DB(), {}
    run(db, state)
    db.rows[0][3]['fills'].append(dict(db.rows[0][3]['fills'][0], client_id='sale',
                                     side='sell', quote_usdt=25.5, fee_usdt=.051))
    text = run(db, state)[0]
    assert 'sell' in text and 'gross 25.5000 USDT' in text and '0.0510' in text
    assert '&lt;private&gt;' in text
