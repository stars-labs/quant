"""Durable live intents, confirmed funding and ledger projection."""

from dataclasses import dataclass
import math
from htx_fill_costs import fee_details


@dataclass
class Holding:
    key: str
    kind: str
    asset: str
    qty: float
    bought: float
    cost: float
    proceeds: float
    opened: object


class OrderStore:
    def __init__(self, conn):
        self.conn = conn
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(597216794, 73961187)")
            if not cur.fetchone()[0]:
                raise RuntimeError("Another live HTX executor holds the lock")

    def pending(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT client_id, asset, side, exchange_id FROM quant.executor_orders "
                        "WHERE venue='HTX' AND environment='live' AND status='pending' "
                        "ORDER BY created_at")
            return cur.fetchall()

    def exists(self, key):
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM quant.executor_orders WHERE venue='HTX' "
                        "AND environment='live' AND action_key=%s", (key,))
            return cur.fetchone() is not None

    def reserve(self, cid, kind, asset, side, action, position, requested, taker, basic):
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO quant.executor_orders
                (client_id,venue,environment,kind,asset,side,action_key,position_key,requested,
                 quoted_taker_rate,quoted_basic_rate)
                VALUES (%s,'HTX','live',%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (venue,environment,action_key) DO NOTHING RETURNING client_id""",
                (cid, kind, asset, side, action, position, requested, taker, basic))
            return cur.fetchone() is not None

    def set_exchange_id(self, cid, oid):
        with self.conn.cursor() as cur:
            cur.execute("UPDATE quant.executor_orders SET exchange_id=%s WHERE client_id=%s",
                        (str(oid), cid))

    def holdings(self):
        with self.conn.cursor() as cur:
            cur.execute("""SELECT position_key,kind,asset,sum(asset_delta),
                sum(CASE WHEN side='buy' THEN asset_delta ELSE 0 END),
                -sum(CASE WHEN side='buy' THEN cash_delta ELSE 0 END),
                sum(CASE WHEN side='sell' THEN cash_delta ELSE 0 END),min(created_at)
                FROM quant.executor_orders WHERE venue='HTX' AND environment='live'
                AND status='done' GROUP BY position_key,kind,asset""")
            return [Holding(r[0],r[1],r[2],*[float(v) for v in r[3:7]],r[7])
                    for r in cur.fetchall()]

    def budget(self, kind, month):
        with self.conn.cursor() as cur:
            if kind == 'trend':
                cur.execute("SELECT coalesce(sum(trend_usdt),0) FROM quant.executor_funding "
                            "WHERE venue='HTX' AND environment='live' AND month<=%s", (month,))
                credit = float(cur.fetchone()[0])
                cur.execute("SELECT coalesce(sum(cash_delta),0) FROM quant.executor_orders "
                            "WHERE venue='HTX' AND environment='live' AND kind='trend' "
                            "AND status='done'")
            else:
                cur.execute("SELECT coalesce(sum(dca_usdt),0) FROM quant.executor_funding "
                            "WHERE venue='HTX' AND environment='live' AND month=%s", (month,))
                credit = float(cur.fetchone()[0])
                cur.execute("SELECT coalesce(sum(cash_delta),0) FROM quant.executor_orders "
                            "WHERE venue='HTX' AND environment='live' AND kind='dca' "
                            "AND status='done' AND (created_at AT TIME ZONE 'UTC')::date >= %s "
                            "AND (created_at AT TIME ZONE 'UTC')::date < (%s::date + interval '1 month')",
                            (month,month))
            return max(0.0, credit + float(cur.fetchone()[0]))

    def expected_cash(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT coalesce(sum(trend_usdt+dca_usdt),0) "
                        "FROM quant.executor_funding WHERE venue='HTX' AND environment='live'")
            credit = float(cur.fetchone()[0])
            cur.execute("SELECT coalesce(sum(cash_delta),0) FROM quant.executor_orders "
                        "WHERE venue='HTX' AND environment='live' AND status='done'")
            return credit + float(cur.fetchone()[0])

    def finish(self, cid, asset_delta, cash_delta, amount, cost):
        # Mark application and update the public execution ledger in ONE transaction.
        # A crash before commit leaves a pending intent to re-query, not a new order.
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("SELECT status,position_key,side,requested FROM quant.executor_orders "
                            "WHERE client_id=%s FOR UPDATE", (cid,))
                status, key, side, requested = cur.fetchone()
                if status == 'done':
                    return
                fee_details(side,asset_delta,cash_delta,amount,cost)
                if not math.isfinite(asset_delta) or not math.isfinite(cash_delta):
                    raise ValueError('Non-finite order movements')
                if side=='buy' and (asset_delta<0 or cash_delta>0 or -cash_delta>float(requested)*1.003+1e-8):
                    raise ValueError('Fill exceeds reserved buy budget')
                if side=='sell' and (asset_delta>0 or cash_delta<0 or -asset_delta>float(requested)*1.003+1e-12):
                    raise ValueError('Fill exceeds reserved sale quantity')
                cur.execute("UPDATE quant.executor_orders SET status='done',asset_delta=%s, "
                            "cash_delta=%s,filled_amount=%s,filled_cost=%s,finished_at=now() "
                            "WHERE client_id=%s", (asset_delta,cash_delta,amount,cost,cid))
                if asset_delta == 0 and cash_delta == 0:
                    return
                h = next(h for h in self.holdings() if h.key == key)
                if h.bought <= 0 or h.qty < -1e-10:
                    raise RuntimeError("Invalid projected holding")
                avg = h.cost / h.bought
                sold = h.bought - h.qty
                closed = h.qty <= h.bought * 1e-10
                pnl = h.proceeds - sold * avg if sold > 0 else None
                quantity = h.bought if closed else h.qty
                trader = f"{'FOLLOW' if h.kind=='trend' else 'DCA'}-HTX"
                strategy = f"{'SignalFollower' if h.kind=='trend' else 'SmartDCA'}-{h.asset}"
                cur.execute("""INSERT INTO quant.nautilus_trades
                    (trader_id,position_id,strategy,instrument,venue,environment,asset_class,
                     open_date,open_rate,quantity,close_date,close_rate,realized_pnl,
                     profit_pct,exit_reason,synced_at)
                    VALUES (%s,%s,%s,%s,'HTX','live','crypto',%s,%s,%s,
                      CASE WHEN %s THEN now() ELSE NULL END,%s,%s,%s,%s,now())
                    ON CONFLICT (trader_id,position_id,open_date) DO UPDATE SET
                      open_rate=EXCLUDED.open_rate,quantity=EXCLUDED.quantity,
                      close_date=EXCLUDED.close_date,close_rate=EXCLUDED.close_rate,
                      realized_pnl=EXCLUDED.realized_pnl,profit_pct=EXCLUDED.profit_pct,
                      exit_reason=EXCLUDED.exit_reason,synced_at=now()""",
                    (trader,h.key,strategy,f'{h.asset}USDT.HTX',h.opened,avg,quantity,closed,
                     h.proceeds/sold if closed else None,pnl,
                     pnl/h.cost if closed else None,'signal' if closed else None))
