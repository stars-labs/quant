"""Funded HTX spot execution. Unknown intents pause trading; never resubmit them."""

import calendar
import math
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from htx_order_store import OrderStore


def fill_deltas(order, trades):
    """Net asset and quote movement from exact match records, including fees."""
    amount = float(order.get('filled') or 0)
    if order.get('filled') is None or not math.isfinite(amount) or amount < 0:
        raise ValueError('Invalid filled amount')
    if amount <= 0:
        return 0.0, 0.0
    base, quote = order['symbol'].split('/')
    if not trades or not math.isclose(sum(float(t['amount']) for t in trades), amount,
                                    rel_tol=1e-8, abs_tol=1e-12):
        raise ValueError('Incomplete order trade details')
    base_fee = quote_fee = cost = 0.0
    for t in trades:
        if not math.isfinite(float(t['amount'])) or float(t['amount']) <= 0 or not math.isfinite(float(t['cost'])) or float(t['cost']) <= 0:
            raise ValueError('Invalid trade amount or cost')
        cost += float(t['cost'])
        fees = t.get('fees') or ([t['fee']] if t.get('fee') is not None else None)
        if not fees:
            raise ValueError('Missing fee information')
        for fee in fees:
            value = float(fee['cost'])
            if not math.isfinite(value):
                raise ValueError('Invalid fee')
            if fee.get('currency') == base:
                base_fee += value
            elif fee.get('currency') == quote:
                quote_fee += value
            elif value != 0:
                raise ValueError('Unsupported third-currency fee')
    if not math.isfinite(cost) or cost <= 0:
        raise ValueError('Invalid filled cost')
    if order.get('cost') is None or not math.isclose(cost,float(order['cost']),rel_tol=1e-8,abs_tol=1e-8):
        raise ValueError('Trade costs differ from order cost')
    if base_fee < 0 or quote_fee < 0 or base_fee >= amount or quote_fee >= cost:
        raise ValueError('Invalid fee totals')
    if order['side'] == 'buy':
        return amount - base_fee, -(cost + quote_fee)
    return -(amount + base_fee), cost - quote_fee


def check_balances(holdings, balance, expected_cash):
    if not math.isfinite(expected_cash):
        raise ValueError('Invalid journal cash')
    expected = defaultdict(float)
    for h in holdings:
        if not math.isfinite(h.qty) or h.qty < -1e-12:
            raise ValueError('Invalid journal quantity')
        expected[h.asset] += max(0, h.qty)
    total = balance['total']
    if any(not math.isfinite(float(q or 0)) or float(q or 0)<0 for q in total.values()):
        raise ValueError('Invalid exchange balance')
    if float(total.get('USDT') or 0) + 0.01 < expected_cash:
        raise ValueError('USDT balance below journal cash')
    for asset in set(expected) | {a for a,q in total.items() if a!='USDT' and q}:
        actual = float(total.get(asset) or 0)
        if not math.isclose(actual, expected[asset], rel_tol=1e-7, abs_tol=1e-12):
            raise ValueError(f'{asset} balance differs from journal')


class LiveHTX:
    def __init__(self, venue, conn, logger):
        if venue.name != 'htx' or venue.mode != 'live':
            raise ValueError('Funded live execution supports HTX only')
        self.venue, self.ex, self.log = venue, venue.ex, logger
        self.account_id = os.environ['HTX_SPOT_ACCOUNT_ID']
        uid = self.ex.spot_private_get_v2_user_uid()
        if uid.get('code') != 200 or str(uid.get('data')) != os.environ['HTX_SUBACCOUNT_UID']:
            raise ValueError('HTX UID mismatch')
        response = self.ex.spot_private_get_v1_account_accounts()
        if response.get('status') != 'ok' or not any(
            str(a['id']) == self.account_id and a['type']=='spot' and a['state']=='working'
            for a in response.get('data',[])
        ):
            raise ValueError('HTX spot account mismatch')
        self.store = OrderStore(conn)

    def reconcile(self):
        for cid, asset, side, oid in self.store.pending():
            symbol = f'{asset}/USDT'
            params = {} if oid else {'clientOrderId':cid}
            # Not-found or timeout leaves the intent pending, stopping new orders.
            order = self.ex.fetch_order(oid or cid, symbol, params)
            if not order.get('id'):
                raise ValueError('Order query lacks order ID')
            if order['symbol'] != symbol or order['side'] != side:
                raise ValueError('Order identity mismatch')
            self.store.set_exchange_id(cid, order['id'])
            if order.get('status') not in ('closed','canceled','expired','rejected'):
                continue
            trades = self.ex.fetch_order_trades(order['id'],symbol) if order.get('filled') else []
            asset_delta, cash_delta = fill_deltas(order,trades)
            self.store.finish(cid,asset_delta,cash_delta)
            self.log(f'HTX/live {side} {asset} reconciled: asset={asset_delta:g} cash={cash_delta:.8f} id={order["id"]}')
        return not self.store.pending()

    def balance(self):
        return self.ex.fetch_balance({'type':'spot','accountId':self.account_id})

    def submit(self, kind, asset, side, action, position, requested):
        symbol = f'{asset}/USDT'
        market = self.ex.market(symbol)
        if not market.get('spot') or market.get('active') is False:
            raise ValueError('Inactive spot market')
        minimum = float((market.get('limits',{}).get('cost') or {}).get('min') or 0)
        balance = self.balance()
        if side == 'buy':
            fee = float(self.ex.fetch_trading_fee(symbol)['taker'])
            if not math.isfinite(fee) or fee < 0 or fee > 0.003:
                raise ValueError('Taker fee exceeds reserved headroom')
            # Reserve quote fee headroom; actual fees are accounted from matches.
            cost = min(requested,float(balance['free'].get('USDT') or 0)) / 1.003
            requested = float(self.ex.cost_to_precision(symbol,cost))
            if requested < minimum or requested <= 0:
                return
            ask = float(self.ex.fetch_ticker(symbol)['ask'])
            qty = float(self.ex.amount_to_precision(symbol,requested / ask))
            min_amount = float((market.get('limits',{}).get('amount') or {}).get('min') or 0)
            if qty < min_amount or qty <= 0:
                return
        else:
            requested = float(self.ex.amount_to_precision(symbol,
                min(requested,float(balance['free'].get(asset) or 0))))
            min_amount = float((market.get('limits',{}).get('amount') or {}).get('min') or 0)
            if requested < min_amount or requested <= 0:
                return
            bid = float(self.ex.fetch_ticker(symbol)['bid'])
            if requested*bid < minimum:
                return  # Preserve dust rather than falsely closing the holding.
        cid = 'q' + uuid.uuid4().hex[:30]
        if not self.store.reserve(cid,kind,asset,side,action,position,requested):
            return
        params = {'clientOrderId':cid,'account-id':self.account_id}
        # Any exception remains journaled as pending. Never auto-resubmit.
        if side == 'buy':
            order = self.ex.create_market_buy_order_with_cost(symbol,requested,params)
        else:
            order = self.ex.create_market_sell_order(symbol,requested,params)
        if order.get('id'):
            self.store.set_exchange_id(cid,order['id'])
        self.reconcile()

    def tick(self):
        if not self.reconcile():
            self.log('HTX/live paused: unfinished order')
            return
        holdings = self.store.holdings()
        check_balances(holdings,self.balance(),self.store.expected_cash())
        conn = self.store.conn
        now = datetime.now(timezone.utc)
        month = now.date().replace(day=1)
        # Signals and their deterministic action keys, same house rule as dry_run.
        import strategy_record as sr
        with conn.cursor() as cur:
            cur.execute("SELECT asset FROM quant.strategy_assets WHERE strategy=%s "
                        "AND updated_at >= now()-interval '3 hours' "
                        "AND last_ts >= now()-interval '3 hours' AND last_ts <= now()",
                        (sr.STRATEGY,))
            if not set(sr.ASSETS).issubset({r[0] for r in cur.fetchall()}):
                raise ValueError('House signal data is stale or incomplete')
            cur.execute('SELECT id,asset FROM quant.strategy_signals '
                        'WHERE strategy=%s AND exit_ts IS NULL', (sr.STRATEGY,))
            signals = {r[1]:str(r[0]) for r in cur.fetchall()}
        # Process exits first to release trend capital. Never sell DCA BTC.
        for h in holdings:
            if h.kind=='trend' and h.qty>1e-12 and h.asset not in signals:
                self.submit('trend',h.asset,'sell',f'exit:{h.key}:{uuid.uuid4().hex}',h.key,h.qty)
                if self.store.pending():
                    return
        for asset in sr.ASSETS:
            if asset not in signals:
                continue
            action = f'entry:{signals[asset]}'
            if self.store.exists(action):
                continue
            amount = min(20.0,self.store.budget('trend',month))
            if amount>0:
                self.submit('trend',asset,'buy',action,f'HTX-signal-{signals[asset]}',amount)
                if self.store.pending():
                    return
        with conn.cursor() as cur:
            cur.execute('SELECT day,units FROM quant.dca_boost_days ORDER BY day DESC LIMIT 1')
            rule = cur.fetchone()
        if not rule or rule[0]!=now.date():
            return
        action = f'dca:{now.date()}'
        if self.store.exists(action):
            return
        units = float(rule[1])
        if not math.isfinite(units) or units<=0:
            raise ValueError('Invalid DCA multiple')
        amount = min(100.0/calendar.monthrange(now.year,now.month)[1]*units,
                     self.store.budget('dca',month))
        if amount>0:
            self.submit('dca','BTC','buy',action,'HTX-DCA-BTC',amount)
