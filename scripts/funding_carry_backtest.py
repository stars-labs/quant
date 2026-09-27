"""Funding-carry backtest: long spot + short USDT-perp, earning (or paying) the perp funding.

Answers "what does the carry the /scan radar points at actually earn after costs?" on Binance
funding history (fapi /fundingRate, public). Daily granularity, no look-ahead: a decision at the
end of day d uses funding up to d and earns funding from d+1.

Costs: opening = spot buy + perp sell, closing = the reverse, each leg a taker fee
(SPOT_FEE 0.1%, PERP_FEE 0.05%) → 0.30% per round trip on the notional, plus ENTRY_SLIP for the
spot/perp spread at each open and close. Capital: returns are quoted on NOTIONAL and on CAPITAL
with 1:1 collateral (half in spot, half as unlevered short margin — the no-liquidation setup),
i.e. capital return = notional return / 2. Basis P&L between open and close is ignored beyond the
slip (it mean-reverts for liquid perps but is a real risk on thin ones).

Caveat: the universe is TODAY's top-40 spot-listed perps by volume (survivorship: coins that
became big); strategies only use a coin once it has 7 days of history.

Usage:
  .venv-bots/bin/python scripts/funding_carry_backtest.py fetch CACHE
  .venv-bots/bin/python scripts/funding_carry_backtest.py run CACHE
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

FAPI = "https://fapi.binance.com/fapi/v1"
SPOT_FEE = 0.001
PERP_FEE = 0.0005
ENTRY_SLIP = 0.0005
LEG = SPOT_FEE + PERP_FEE + ENTRY_SLIP        # cost of one open or one close, on notional
START = dt.date(2024, 1, 1)


def fetch(cache: Path) -> None:
    t = requests.get(f"{FAPI}/ticker/24hr", timeout=30).json()
    spot = {x["symbol"] for x in requests.get("https://api.binance.com/api/v3/ticker/price",
                                              timeout=30).json()}
    base = lambda s: re.sub(r"^\d+", "", s[:-4])  # noqa: E731
    perps = sorted((x for x in t if x["symbol"].endswith("USDT") and base(x["symbol"]) + "USDT" in spot),
                   key=lambda x: -float(x["quoteVolume"]))[:40]
    syms = [x["symbol"] for x in perps]
    start = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    for s in syms:
        p = cache / f"{s}.pkl"
        if p.exists():
            continue
        rows, st = [], start
        while True:
            r = requests.get(f"{FAPI}/fundingRate", params={"symbol": s, "startTime": st,
                                                           "limit": 1000}, timeout=30).json()
            rows += [(int(x["fundingTime"]), float(x["fundingRate"])) for x in r]
            if len(r) < 1000:
                break
            st = int(r[-1]["fundingTime"]) + 1
            time.sleep(0.2)
        pickle.dump(rows, open(p, "wb"))
        print(s, len(rows), flush=True)
    json.dump(syms, open(cache / "syms.json", "w"))


def daily(rows: list[tuple[int, float]]) -> dict[dt.date, float]:
    """Funding summed per UTC day (interval-agnostic: 1h/4h/8h settlements all just add up)."""
    d: dict[dt.date, float] = defaultdict(float)
    for ms, r in rows:
        d[dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date()] += r
    return dict(d)


def ann(x: float, days: int) -> float:
    return x * 365 / days if days else 0.0


def always_on(f: dict[dt.date, float], days: list[dt.date]) -> tuple[float, list[float]]:
    """Hold the carry every day of `days`: one open + one close."""
    daily_pnl = [f.get(d, 0.0) for d in days]
    daily_pnl[0] -= LEG
    daily_pnl[-1] -= LEG
    return sum(daily_pnl), daily_pnl


def threshold(f: dict[dt.date, float], days: list[dt.date], enter: float, leave: float
              ) -> tuple[float, list[float], int]:
    """Open when trailing-7d annualised funding > enter, close when < leave."""
    held, pnl, trips = False, [], 0
    hist: list[float] = []
    for d in days:
        p = f.get(d, 0.0) if held else 0.0
        hist.append(f.get(d, 0.0))
        trail = ann(sum(hist[-7:]), 7) if len(hist) >= 7 else None
        if trail is not None and not held and trail > enter:
            held, p = True, p - LEG
            trips += 1
        elif held and trail is not None and trail < leave:
            held, p = False, p - LEG
        pnl.append(p)
    if held:
        pnl[-1] -= LEG
    return sum(pnl), pnl, trips


def rotation(fs: dict[str, dict[dt.date, float]], days: list[dt.date], n: int, floor: float
             ) -> tuple[float, list[float], float]:
    """Every 7 days hold the top-n coins by trailing-7d annualised funding (> floor), equal
    weight on one unit of notional; pay LEG on every weight that changes hands."""
    w: dict[str, float] = {}
    pnl, turnover = [], 0.0
    for i, d in enumerate(days):
        p = sum(wt * fs[s].get(d, 0.0) for s, wt in w.items())
        if i % 7 == 6:
            trail = {s: ann(sum(f.get(days[j], 0.0) for j in range(i - 6, i + 1)), 7)
                     for s, f in fs.items()
                     if sum(1 for j in range(i - 6, i + 1) if days[j] in f) == 7}
            pick = [s for s, v in sorted(trail.items(), key=lambda kv: -kv[1]) if v > floor][:n]
            new = {s: 1 / len(pick) for s in pick}
            change = sum(abs(new.get(s, 0) - w.get(s, 0)) for s in set(new) | set(w))
            p -= change * LEG
            turnover += change
            w = new
        pnl.append(p)
    pnl[-1] -= sum(w.values()) * LEG
    return sum(pnl), pnl, turnover


def mdd(pnl: list[float]) -> float:
    eq = peak = worst = 0.0
    for x in pnl:
        eq += x
        peak = max(peak, eq)
        worst = min(worst, eq - peak)
    return worst


def by_year(pnl: list[float], days: list[dt.date]) -> str:
    out = []
    for y in sorted({d.year for d in days}):
        idx = [i for i, d in enumerate(days) if d.year == y]
        out.append(f"{y} {ann(sum(pnl[i] for i in idx), len(idx)) * 100:+.1f}%")
    return "  ".join(out)


def run(cache: Path) -> None:
    syms = json.load(open(cache / "syms.json"))
    fs = {s: {d: v for d, v in daily(pickle.load(open(cache / f"{s}.pkl", "rb"))).items()
              if d >= START} for s in syms}
    fs = {s: f for s, f in fs.items() if len(f) >= 30}
    end = max(max(f) for f in fs.values())
    days = [START + dt.timedelta(days=i) for i in range((end - START).days)]  # drop the partial day
    n = len(days)
    print(f"{len(fs)} perps, {days[0]} .. {days[-1]} ({n} days). Returns annualised, ON NOTIONAL "
          f"(on capital with 1:1 collateral = half). Costs {LEG * 2 * 100:.2f}% per round trip.\n")

    print("A. always-on carry (one open, one close)")
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"):
        tot, pnl = always_on(fs[s], days)
        neg = sum(1 for d in days if fs[s].get(d, 0) < 0) / n
        print(f"  {s:10} {ann(tot, n) * 100:+6.1f}%/yr  maxDD {mdd(pnl) * 100:5.2f}%  "
              f"negative-funding days {neg * 100:3.0f}%   {by_year(pnl, days)}")

    print("\nB. per-coin threshold (open > enter, close < leave; trailing 7d annualised)")
    for enter, leave in ((0.20, 0.05), (0.30, 0.10)):
        res = []
        for s, f in fs.items():
            live = [d for d in days if d >= min(f)]
            if len(live) < 90:
                continue
            tot, pnl, trips = threshold(f, live, enter, leave)
            res.append((s, ann(tot, len(live)), trips, mdd(pnl)))
        res.sort(key=lambda r: -r[1])
        avg = sum(r[1] for r in res) / len(res)
        pos = sum(r[1] > 0 for r in res)
        print(f"  enter {enter:.0%} / leave {leave:.0%}: mean {avg * 100:+.1f}%/yr over {len(res)} coins, "
              f"{pos}/{len(res)} positive; best " +
              ", ".join(f"{s[:-4]} {a * 100:+.0f}% ({t} trips)" for s, a, t, _ in res[:4]) +
              "; worst " + ", ".join(f"{s[:-4]} {a * 100:+.0f}%" for s, a, _, _ in res[-3:]))

    print("\nC. weekly rotation into the top-n coins by trailing funding")
    for top, floor in ((3, 0.10), (5, 0.10), (5, 0.20), (10, 0.10)):
        tot, pnl, turnover = rotation(fs, days, top, floor)
        print(f"  top {top:2} (> {floor:.0%}/yr): {ann(tot, n) * 100:+6.1f}%/yr  maxDD {mdd(pnl) * 100:5.2f}%  "
              f"turnover {turnover / (n / 365):.1f}x/yr   {by_year(pnl, days)}")


def main() -> int:
    cmd, cache = sys.argv[1], Path(sys.argv[2])
    cache.mkdir(parents=True, exist_ok=True)
    (fetch if cmd == "fetch" else run)(cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
