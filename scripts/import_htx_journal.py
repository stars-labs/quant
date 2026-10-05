"""One-time cutover from the retired hosted journal; never submits an order.

Input is a private JSON snapshot with funding/orders arrays. Stop the old executor
and acquire its advisory lock before exporting it. Import into an empty journal,
then reconcile with HTX before starting the local service.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from starslab_runner.journal import Journal, finite


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Snapshot timestamps must include a timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def import_snapshot(store, snapshot, uid, spot_id):
    if set(snapshot) != {'funding', 'orders'}:
        raise ValueError('Invalid snapshot fields')
    identity = json.dumps(['htx', 'live', str(uid), str(spot_id)])
    with store.transaction():
        if any(store.db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
               for table in ('funding', 'orders', 'metadata')):
            raise ValueError('Destination journal must be empty')
        store.db.execute('INSERT INTO metadata VALUES (?,?)', ('account', identity))
        for row in snapshot['funding']:
            month = datetime.fromisoformat(row['month']).date()
            trend, dca = finite(row['trend_usdt']), finite(row['dca_usdt'])
            if month.day != 1 or min(trend, dca) < 0 or trend + dca <= 0:
                raise ValueError('Invalid funding')
            store.db.execute('INSERT INTO funding VALUES (?,?,?)',
                             (month.isoformat(), trend, dca))
        for row in snapshot['orders']:
            if row['venue'] != 'HTX' or row['environment'] != 'live':
                raise ValueError('Snapshot contains another account mode')
            position = row['position_key']
            if row['kind'] == 'trend' and position.startswith('HTX-signal-'):
                position = 'signal:' + str(int(position.removeprefix('HTX-signal-')))
            elif row['kind'] == 'dca' and position == 'HTX-DCA-BTC' and row['asset'] == 'BTC':
                position = 'DCA-BTC'
            else:
                raise ValueError('Unexpected position identity')
            if row['side'] not in ('buy', 'sell') or row['status'] not in ('done', 'pending'):
                raise ValueError('Invalid order state')
            requested = finite(row['requested'])
            if requested <= 0:
                raise ValueError('Invalid reservation')
            # The old reservation excluded fees. Retain its original safety cap.
            requested *= 1.003
            values = [row.get(k) for k in ('asset_delta', 'cash_delta', 'filled_amount', 'filled_cost')]
            if row['status'] == 'done':
                values = list(map(finite, values))
                qty, cash, amount, cost = values
                if amount < 0 or cost < 0 or (row['side'] == 'buy' and (qty < 0 or cash > 0)) or (
                        row['side'] == 'sell' and (qty > 0 or cash < 0)):
                    raise ValueError('Invalid terminal movements')
                if (-cash if row['side'] == 'buy' else -qty) > requested + 1e-8:
                    raise ValueError('Fill exceeds original reservation')
                if any(values):
                    if amount <= 0 or cost <= 0:
                        raise ValueError('Missing gross fill accounting')
                    base_fee = amount - qty if row['side'] == 'buy' else -qty - amount
                    quote_fee = -cash - cost if row['side'] == 'buy' else cost - cash
                    if base_fee < -max(1e-12, amount * 1e-10) or quote_fee < -max(1e-8, cost * 1e-10):
                        raise ValueError('Inconsistent fee movements')
                    if (max(0, base_fee) * cost / amount + max(0, quote_fee)) / cost > .003 + 1e-8:
                        raise ValueError('Historical fill exceeds fee ceiling')
            elif any(v not in (None, 0) for v in values):
                raise ValueError('Pending order has terminal movements')
            else:
                values = [None] * 4
            rates = [row.get(k) for k in ('quoted_taker_rate', 'quoted_basic_rate')]
            if any(v is None for v in rates) or any(not 0 <= finite(v) <= .003 for v in rates):
                raise ValueError('Missing or unsafe quoted fee')
            store.db.execute('''INSERT INTO orders VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (row['client_id'], row['action_key'], position, row['kind'], row['asset'],
                 row['side'], requested, row['status'], row.get('exchange_id'),
                 *map(finite, rates), *values, timestamp(row['created_at']),
                 timestamp(row['finished_at']) if row['finished_at'] else None))
        if store.cash() < -1e-8 or any(h['quantity'] < -1e-12 for h in store.holdings()):
            raise ValueError('Snapshot has negative cash or holdings')
        if len(store.pending()) > 1:
            raise ValueError('Multiple pending orders require manual reconciliation')
    return {'orders': len(snapshot['orders']), 'pending': len(store.pending()),
            'cash_usdt': store.cash(), 'positions': len(store.holdings())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('journal', type=Path)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--spot-id', required=True)
    args = parser.parse_args()
    store = Journal(args.journal)
    try:
        result = import_snapshot(store, json.loads(args.snapshot.read_text()), args.uid, args.spot_id)
        print(json.dumps(result))
    finally:
        store.close()


if __name__ == '__main__':
    main()
