"""Actual fee arithmetic from gross fills and already-reconciled net movements."""

import math


def fee_details(side, asset_delta, cash_delta, amount, cost):
    values = [float(v) for v in (asset_delta, cash_delta, amount, cost)]
    qty, cash, amount, cost = values
    if side not in ('buy', 'sell') or any(not math.isfinite(v) for v in values):
        raise ValueError('Invalid gross fill')
    if amount == cost == qty == cash == 0:
        return 0.0, 0.0, 0.0, 0.0
    if amount <= 0 or cost <= 0:
        raise ValueError('Invalid gross fill')
    base = amount-qty if side=='buy' else -qty-amount
    quote = -cash-cost if side=='buy' else cost-cash
    if base < -max(1e-12,amount*1e-10) or quote < -max(1e-8,cost*1e-10):
        raise ValueError('Gross fill differs from net journal')
    base, quote = max(0.0,base), max(0.0,quote)
    equivalent = base*cost/amount + quote
    rate = equivalent/cost
    if rate > .003+1e-8:
        raise ValueError('Actual fee exceeds safety ceiling')
    return base,quote,equivalent,rate


def quantity(value):
    return f'{abs(float(value)):.12f}'.rstrip('0').rstrip('.') or '0'
