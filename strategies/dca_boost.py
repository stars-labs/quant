"""Smart-DCA "boost day" rule — pure, stdlib only.

Mirrors nautilus_crypto/accumulator.py (AccumulatorConfig defaults, mode='smart') so the
Telegram "定投加倍日" push says exactly what the live accumulator does:
  units = 1 (base buy)
        + 5 if FNG <= 15 (deep fear)   else + 3 if FNG <= 25 (fear)
        + 2 if close <= 80% of the highest HIGH of the last 30 daily bars (dip; stacks)
The 30-bar window includes the current bar, as in Accumulator.on_bar.

simulate() replays the rule over a daily history to compare the smart DCA's average cost
with a plain fixed-amount DCA over the same days — the honest "does it help" number.
"""

from __future__ import annotations

FEAR = 25
FEAR_ADD = 3.0
DEEP_FEAR = 15
DEEP_FEAR_ADD = 5.0
DIP_LOOKBACK = 30
DIP = 0.20
DIP_ADD = 2.0

# (day 'YYYY-MM-DD', fng, high, close) — one closed daily BTC bar and that day's FNG
Day = tuple[str, int, float, float]


def units(fng: int, close: float, highs: list[float]) -> dict:
    """highs = HIGHs of the last DIP_LOOKBACK bars INCLUDING the current one. The dip
    boost needs a full window (the accumulator skips it until its deque is full)."""
    fear_add = DEEP_FEAR_ADD if fng <= DEEP_FEAR else FEAR_ADD if fng <= FEAR else 0.0
    high = max(highs) if len(highs) >= DIP_LOOKBACK else None
    drawdown = close / high - 1 if high else None
    # Same comparison as the accumulator (not drawdown <= -DIP: float edge at exactly 20%).
    dip_add = DIP_ADD if high and close <= high * (1 - DIP) else 0.0
    return {"units": 1.0 + fear_add + dip_add, "fear_add": fear_add, "dip_add": dip_add,
            "high_30d": high, "drawdown": drawdown}


def simulate(days: list[Day], from_day: str) -> dict | None:
    """Buy 1 unit/day (plain) vs units()/day (smart) at each close on/after from_day.
    Earlier days only warm the 30-day high window. Costs are USD per BTC."""
    plain_usd = plain_btc = smart_usd = smart_btc = 0.0
    boosted = 0
    for i, (day, fng, _high, close) in enumerate(days):
        if day < from_day:
            continue
        highs = [d[2] for d in days[max(0, i - DIP_LOOKBACK + 1): i + 1]]
        u = units(fng, close, highs)["units"]
        plain_usd += 1.0
        plain_btc += 1.0 / close
        smart_usd += u
        smart_btc += u / close
        boosted += u > 1
    if not plain_btc:
        return None
    plain_cost, smart_cost = plain_usd / plain_btc, smart_usd / smart_btc
    return {"days": int(plain_usd), "boosted_days": boosted,
            "plain_cost": plain_cost, "smart_cost": smart_cost,
            "cost_diff": smart_cost / plain_cost - 1}
