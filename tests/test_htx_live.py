"""Offline live-order reconciliation and account isolation checks."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'strategies'))
from htx_live import LiveHTX, account_taker_fee, check_balances, fill_deltas


def order(side='buy', filled=0.01, cost=600, status='closed'):
    return dict(id='42', symbol='BTC/USDT', side=side, filled=filled,
                cost=cost, status=status)


def trade(amount=0.01, cost=600, currency='BTC', fee=0.00002):
    return dict(amount=amount, cost=cost, fee=dict(currency=currency, cost=fee))


def test_authenticated_effective_fee_not_basic_rate():
    ex = SimpleNamespace(fetch_trading_fee=lambda symbol: {
        'symbol': symbol, 'taker': .0015, 'info': {'takerFeeRate': '.002'}})
    assert account_taker_fee(ex, 'BTC/USDT') == .0015
    ex.fetch_trading_fee = lambda symbol: {'symbol': symbol, 'taker': 0}
    assert account_taker_fee(ex, 'BTC/USDT') == 0


def test_match_fee_overrides_advertised_discount_for_net_holdings():
    ex = SimpleNamespace(fetch_trading_fee=lambda symbol: {
        'symbol': symbol, 'taker': .0015, 'info': {'takerFeeRate': '.002'}})
    assert account_taker_fee(ex, 'BTC/USDT') == .0015
    qty, cash = fill_deltas(order(), [trade(fee=.00002)])
    assert math.isclose(qty,.01*(1-.002)) and cash == -600
    assert not math.isclose(qty,.01*(1-.0015))


def test_bad_account_fee_never_falls_back_to_default():
    for rate in [None, float('nan'), float('inf'), -.001, .0031]:
        ex = SimpleNamespace(fetch_trading_fee=lambda symbol: {'symbol': symbol, 'taker': rate})
        rejects(lambda: account_taker_fee(ex, 'BTC/USDT'), 'fee')
    ex.fetch_trading_fee = lambda symbol: {'symbol': 'ETH/USDT', 'taker': .0015}
    rejects(lambda: account_taker_fee(ex, 'BTC/USDT'), 'symbol mismatch')
    ex.fetch_trading_fee = lambda symbol: {
        'symbol': symbol, 'taker': .0015, 'info': {'takerFeeRate': '.004'}}
    rejects(lambda: account_taker_fee(ex, 'BTC/USDT'), 'headroom')


def test_fee_api_timeout_never_uses_a_cached_public_rate():
    def timeout(symbol): raise TimeoutError()
    try:
        account_taker_fee(SimpleNamespace(fetch_trading_fee=timeout), 'BTC/USDT')
    except TimeoutError:
        return
    raise AssertionError('Fee query failure must propagate')


def test_unsettled_deduction_keeps_order_pending():
    t = trade()
    t['info'] = {'fee-deduct-state': 'ongoing', 'filled-points': '0'}
    obj = live(matches=[t])
    rejects(obj.reconcile, 'not final')
    assert obj.store.pending() and not obj.store.finished


def test_raw_third_currency_deduction_cannot_be_hidden_by_ccxt_fee():
    t = trade()
    t['info'] = {'fee-deduct-state': 'done', 'filled-points': '.001', 'fee-deduct-currency': 'ht'}
    rejects(lambda: fill_deltas(order(), [t]), 'third-currency')
    t['info']['filled-points'] = 'nan'
    rejects(lambda: fill_deltas(order(), [t]), 'Invalid deducted fee')


def test_sale_queries_effective_fee_before_reserving_order():
    obj = live(side='sell')
    obj.account_id = 'account7'
    obj.balance = lambda: {'free': {'BTC': .01}}
    obj.ex.market = lambda symbol: {'spot': True, 'limits': {'cost': {'min': 5}}}
    obj.ex.amount_to_precision = lambda symbol, value: str(value)
    obj.ex.fetch_ticker = lambda symbol: {'bid': 60000}
    queries = []
    def fail_fee(symbol):
        queries.append(symbol)
        raise TimeoutError()
    obj.ex.fetch_trading_fee = fail_fee
    obj.store.reserve = lambda *args: (_ for _ in ()).throw(AssertionError('No intent before fee'))
    try:
        obj.submit('trend', 'BTC', 'sell', 'exit:1', 'position1', .01)
    except TimeoutError:
        pass
    else:
        raise AssertionError('Missing fee must prevent sale')
    assert queries==['BTC/USDT']


def rejects(fn, text):
    try:
        fn()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError('Expected rejection: ' + text)


def test_buy_base_fee_reduces_owned_quantity():
    qty, cash = fill_deltas(order(), [trade()])
    assert math.isclose(qty, 0.00998)
    assert cash == -600


def test_buy_quote_fee_increases_cash_cost():
    assert fill_deltas(order(), [trade(currency='USDT', fee=1.2)]) == (0.01, -601.2)


def test_partial_canceled_sell_applies_only_actual_fill():
    qty, cash = fill_deltas(order('sell', 0.004, 240, 'canceled'),
                            [trade(0.004, 240, 'USDT', 0.48)])
    assert qty == -0.004
    assert math.isclose(cash, 239.52)
    assert math.isclose(0.01 + qty, 0.006)


def test_multiple_matches_and_fee_list_are_summed():
    matches = [dict(amount=0.004, cost=240, fees=[dict(currency='BTC', cost=0.000008)]),
               dict(amount=0.006, cost=360, fees=[dict(currency='BTC', cost=0.000012)])]
    qty, cash = fill_deltas(order(), matches)
    assert math.isclose(qty, 0.00998) and cash == -600


def test_incomplete_match_details_rejected():
    rejects(lambda: fill_deltas(order(), [trade(0.004, 240)]), 'Incomplete')


def test_match_cost_mismatch_rejected():
    rejects(lambda: fill_deltas(order(), [trade(cost=599)]), 'costs differ')


def test_missing_fee_and_third_currency_rejected():
    rejects(lambda: fill_deltas(order(), [dict(amount=0.01, cost=600)]), 'Missing fee')
    rejects(lambda: fill_deltas(order(), [trade(currency='HT', fee=0.001)]), 'third-currency')


def test_invalid_amount_fee_and_cost_rejected():
    rejects(lambda: fill_deltas(order(filled=float('nan')), []), 'filled amount')
    rejects(lambda: fill_deltas(order(), [trade(fee=float('inf'))]), 'Invalid fee')
    rejects(lambda: fill_deltas(order(cost=0), [trade(cost=0)]), 'trade amount or cost')


def test_canceled_zero_fill_changes_nothing():
    assert fill_deltas(order(filled=0, cost=0, status='canceled'), []) == (0, 0)


def test_btc_balance_combines_trend_and_dca_net_quantities():
    holdings = [SimpleNamespace(asset='BTC', qty=0.001996, kind='trend'),
                SimpleNamespace(asset='BTC', qty=0.003992, kind='dca')]
    check_balances(holdings, {'total': {'BTC': 0.005988, 'USDT': 80}}, 80)
    rejects(lambda: check_balances(holdings, {'total': {'BTC': 0.006, 'USDT': 80}}, 80),
            'BTC balance differs')


def test_untracked_assets_and_insufficient_cash_rejected():
    rejects(lambda: check_balances([], {'total': {'USDT': 200, 'ETH': 0.1}}, 200),
            'ETH balance differs')
    rejects(lambda: check_balances([], {'total': {'USDT': 99}}, 100), 'USDT balance')
    check_balances([], {'total': {'USDT': 250}}, 200)


class FakeStore:
    def __init__(self, side='buy'):
        self.rows = [('client1', 'BTC', side, None)]
        self.finished = []
        self.reservations = []

    def pending(self):
        return self.rows.copy()

    def set_exchange_id(self, cid, oid):
        self.rows = [(c, a, s, oid if c == cid else o) for c, a, s, o in self.rows]

    def finish(self, cid, qty, cash):
        self.finished.append((cid, qty, cash))
        self.rows = [r for r in self.rows if r[0] != cid]


class FakeExchange:
    def __init__(self, result=None, matches=None):
        self.result = result or order()
        self.matches = matches if matches is not None else [trade()]
        self.timeout = False
        self.queries = []
        self.creates = 0

    def fetch_order(self, oid, symbol, params):
        self.queries.append((oid, symbol, params))
        if self.timeout:
            raise TimeoutError('uncertain exchange result')
        return self.result.copy()

    def fetch_order_trades(self, oid, symbol):
        return self.matches

    def create_market_buy_order_with_cost(self, *args):
        self.creates += 1
        raise AssertionError('Reconciliation must never submit orders')


def live(result=None, matches=None, side='buy'):
    obj = LiveHTX.__new__(LiveHTX)
    obj.store = FakeStore(side)
    obj.ex = FakeExchange(result, matches)
    obj.log = lambda message: None
    return obj


def test_timeout_then_recovery_looks_up_client_id_without_resubmission():
    obj = live()
    obj.ex.timeout = True
    try:
        obj.reconcile()
    except TimeoutError:
        pass
    else:
        raise AssertionError('Timeout must propagate')
    assert obj.store.pending() and not obj.store.finished
    obj.ex.timeout = False
    assert obj.reconcile()
    assert obj.ex.queries == [('client1', 'BTC/USDT', {'clientOrderId': 'client1'})] * 2
    assert obj.ex.creates == 0
    assert len(obj.store.finished) == 1
    assert obj.reconcile() and len(obj.store.finished) == 1


def test_open_partial_order_stays_pending_until_terminal():
    obj = live(order(status='open'))
    assert not obj.reconcile()
    assert not obj.store.finished
    obj.ex.result['status'] = 'closed'
    assert obj.reconcile()
    assert obj.ex.queries[-1] == ('42', 'BTC/USDT', {})


def test_incomplete_terminal_trades_remain_pending():
    obj = live(matches=[trade(0.004, 240)])
    rejects(obj.reconcile, 'Incomplete')
    assert obj.store.pending() and not obj.store.finished
    assert obj.ex.creates == 0


def test_terminal_partial_sell_reconciles_net_proceeds():
    obj = live(order('sell', 0.004, 240, 'canceled'),
               [trade(0.004, 240, 'USDT', 0.48)], 'sell')
    assert obj.reconcile()
    _, qty, cash = obj.store.finished[0]
    assert qty == -0.004 and math.isclose(cash, 239.52)


def test_wrong_order_identity_remains_pending():
    result = order()
    result['symbol'] = 'ETH/USDT'
    obj = live(result)
    rejects(obj.reconcile, 'identity mismatch')
    assert obj.store.pending() and not obj.store.finished


def test_submit_timeout_persists_intent_and_recovery_never_recreates():
    obj = live()
    obj.store.rows = []
    obj.account_id = 'account7'
    calls = []
    def reserve(cid, kind, asset, side, action, position, requested):
        obj.store.rows.append((cid, asset, side, None))
        return True
    obj.store.reserve = reserve
    obj.balance = lambda: {'free': {'USDT': 200}}
    obj.ex.market = lambda symbol: {'spot': True, 'active': True,
                                   'limits': {'cost': {'min': 5}, 'amount': {'min': 0.00001}}}
    obj.ex.fetch_trading_fee = lambda symbol: {'symbol': symbol, 'taker': 0.002}
    obj.ex.cost_to_precision = lambda symbol, value: str(value)
    obj.ex.amount_to_precision = lambda symbol, value: str(value)
    obj.ex.fetch_ticker = lambda symbol: {'ask': 60000}
    def timed_out_create(symbol, cost, params):
        calls.append((symbol, cost, params))
        raise TimeoutError('exchange accepted but response lost')
    obj.ex.create_market_buy_order_with_cost = timed_out_create
    try:
        obj.submit('trend', 'BTC', 'buy', 'entry:8', 'position8', 20)
    except TimeoutError:
        pass
    else:
        raise AssertionError('Submission timeout must propagate')
    cid = obj.store.pending()[0][0]
    assert calls[0][2] == {'clientOrderId': cid, 'account-id': 'account7'}
    assert len(cid) <= 64 and not obj.store.finished
    assert obj.reconcile()
    assert len(calls) == 1
    assert obj.ex.queries == [(cid, 'BTC/USDT', {'clientOrderId': cid})]


class TickCursor:
    def __init__(self, store):
        self.store = store
        self.query = ''

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.store.queries.append((query, params))

    def fetchall(self):
        if 'strategy_assets' in self.query:
            return [(a,) for a in self.store.fresh_assets]
        return self.store.signals

    def fetchone(self):
        return self.store.rule


class TickStore:
    def __init__(self):
        import strategy_record as sr
        from datetime import datetime, timezone
        self.fresh_assets = list(sr.ASSETS)
        self.signals = [('8', sr.ASSETS[0])]
        self.rule = (datetime.now(timezone.utc).date(), 1)
        self.cash = {'trend': 100.0, 'dca': 100.0}
        self.actions = set()
        self.queries = []
        self.positions = []
        self.rows = []
        self.conn = SimpleNamespace(cursor=lambda: TickCursor(self))

    def pending(self):
        return self.rows

    def holdings(self):
        return self.positions

    def expected_cash(self):
        return 200

    def budget(self, kind, month):
        assert month.day == 1
        return self.cash[kind]

    def exists(self, action):
        return action in self.actions


def ticking():
    obj = LiveHTX.__new__(LiveHTX)
    obj.store = TickStore()
    obj.log = lambda msg: None
    obj.reconcile = lambda: not obj.store.pending()
    obj.balance = lambda: {'total': {'USDT': 200}}
    obj.submitted = []
    def submit(kind, asset, side, action, position, requested):
        obj.submitted.append((kind, asset, side, action, position, requested))
        obj.store.actions.add(action)
        if side == 'buy':
            obj.store.cash[kind] -= requested
    obj.submit = submit
    return obj


def test_tick_trend_twenty_and_dca_calendar_month_allocation():
    import calendar
    from datetime import datetime, timezone
    obj = ticking()
    obj.tick()
    assert len(obj.submitted) == 2
    assert obj.submitted[0][0] == 'trend' and obj.submitted[0][-1] == 20
    now = datetime.now(timezone.utc)
    dca = obj.submitted[1]
    assert dca[0:3] == ('dca', 'BTC', 'buy')
    assert dca[3] == f'dca:{now.date()}'
    assert math.isclose(dca[-1], 100/calendar.monthrange(now.year, now.month)[1])


def test_tick_trend_cap_and_dca_boost_never_exceed_remaining_funding():
    obj = ticking()
    obj.store.cash = {'trend': 7.5, 'dca': 1.25}
    obj.store.rule = (obj.store.rule[0], 100)
    obj.tick()
    assert obj.submitted[0][-1] == 7.5
    assert obj.submitted[1][-1] == 1.25
    assert obj.store.cash == {'trend': 0, 'dca': 0}


def test_tick_unresolved_order_prevents_all_actions_and_reads():
    obj = ticking()
    obj.store.rows = [('pending',)]
    obj.balance = lambda: (_ for _ in ()).throw(AssertionError('No balance read expected'))
    obj.tick()
    assert not obj.submitted and not obj.store.queries


def test_tick_stale_or_incomplete_house_data_blocks_both_strategies():
    obj = ticking()
    obj.store.fresh_assets.pop()
    rejects(obj.tick, 'stale or incomplete')
    assert not obj.submitted
    query = obj.store.queries[0][0]
    assert 'updated_at' in query and 'last_ts' in query and 'last_ts <= now()' in query


def test_tick_repeated_signal_and_day_never_submit_twice():
    obj = ticking()
    obj.tick()
    first = obj.submitted.copy()
    obj.tick()
    assert obj.submitted == first


def test_tick_no_confirmed_funding_means_no_buys():
    obj = ticking()
    obj.store.cash = {'trend': 0, 'dca': 0}
    obj.tick()
    assert not obj.submitted


def test_tick_wrong_dca_date_never_buys_dca():
    from datetime import timedelta
    obj = ticking()
    obj.store.signals = []
    obj.store.rule = (obj.store.rule[0] - timedelta(days=1), 2)
    obj.tick()
    assert not obj.submitted


def test_nonfinite_balances_and_negative_trade_amounts_are_rejected():
    rejects(lambda: check_balances([], {'total': {'USDT': float('nan')}}, 200), 'Invalid exchange')
    rejects(lambda: check_balances([], {'total': {'USDT': 200}}, float('nan')), 'Invalid journal')
    rejects(lambda: fill_deltas(order(), [trade(-0.001, -60), trade(0.011, 660)]), 'Invalid trade')
