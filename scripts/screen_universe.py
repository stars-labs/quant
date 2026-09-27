"""Universe screen for the house Donchian 1h rule (strategies/strategy_record.py).

Selection must never look at the period it will be shown on: pick assets on an in-sample
window, verify/publish on the out-of-sample one. 2026-09-27 run: in-sample 2024-01-01 ..
2025-12-31, out-of-sample 2026-01-01 .. now (results in STRATEGY_LEADERBOARD.md).

Pre-registered criteria (in-sample only): two full years of data, net return > 0 (0.1%/side
fees), strategy max drawdown shallower than buy-and-hold's, return / |max drawdown| >= 0.5.

Usage (CACHE = any scratch dir; Binance public klines, no key):
  .venv-bots/bin/python scripts/screen_universe.py fetch CACHE   # top-30 USDT pairs, 1h since 2023-12-24
  .venv-bots/bin/python scripts/screen_universe.py is CACHE      # in-sample table + selection
  .venv-bots/bin/python scripts/screen_universe.py oos CACHE     # out-of-sample table + group comparison
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))
import strategy_record as sr  # noqa: E402

STABLE = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "USD1", "XUSD", "RLUSD",
          "USDE", "BFUSD", "PAXG", "WBTC", "WBETH", "BNSOL"}
KLINES = "https://api.binance.com/api/v3/klines"


def _ms(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


PERIODS = {"is": (_ms(2024, 1, 1), _ms(2026, 1, 1)), "oos": (_ms(2026, 1, 1), 10**15)}


def fetch(cache: Path) -> None:
    t = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=30).json()
    rows = [x for x in t if x["symbol"].endswith("USDT") and x["symbol"][:-4] not in STABLE
            and not any(k in x["symbol"] for k in ("UPUSDT", "DOWNUSDT", "BULL", "BEAR"))]
    rows.sort(key=lambda x: -float(x["quoteVolume"]))
    top = [x["symbol"][:-4] for x in rows[:30]]
    print("top30:", top)
    now = time.time() * 1000
    for a in top:
        p = cache / f"{a}.pkl"
        if p.exists():
            continue
        bars, s = [], _ms(2023, 12, 24)
        while True:
            r = requests.get(KLINES, params={"symbol": a + "USDT", "interval": "1h",
                                             "startTime": s, "limit": 1000}, timeout=30).json()
            bars += [(int(k[6]), float(k[2]), float(k[3]), float(k[4])) for k in r if int(k[6]) <= now]
            if len(r) < 1000:
                break
            s = int(r[-1][6]) + 1
        pickle.dump(bars, open(p, "wb"))
        print(a, len(bars), flush=True)
    json.dump(top, open(cache / "top.json", "w"))


def run(bars: list, a: int, b: int) -> dict | None:
    """Replay the rule on [a, b): trades net of fees (an open trade marked at the last close)."""
    seg = [x for x in bars if x[0] < b]
    first = next((i for i, x in enumerate(seg) if x[0] >= a), None)
    if first is None or first < sr.ENTRY_LB or len(seg) - first < 24 * 180:
        return None
    f = (1 - sr.FEE) ** 2
    trades, pos = [], None
    for e in sr.step(seg, None, after_ms=a):
        if e["type"] == "entry":
            pos = e
        else:
            trades.append(e["price"] / pos["price"] * f - 1)
            pos = None
    if pos:
        trades.append(seg[-1][3] / pos["price"] * f - 1)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in trades:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    closes = [x[3] for x in seg[first:]]
    hpeak, hmdd = closes[0], 0.0
    for c in closes:
        hpeak = max(hpeak, c)
        hmdd = min(hmdd, c / hpeak - 1)
    return {"n": len(trades), "win": sum(r > 0 for r in trades) / len(trades) if trades else 0.0,
            "ret": eq - 1, "mdd": mdd, "hold": closes[-1] / closes[0] - 1, "hold_mdd": hmdd,
            "years": (len(seg) - first) / 24 / 365}


def selected(is_: dict) -> list[str]:
    return sorted(a for a, r in is_.items() if r["years"] >= 1.99 and r["ret"] > 0
                  and r["mdd"] > r["hold_mdd"] and r["ret"] / abs(r["mdd"]) >= 0.5)


def main() -> int:
    cmd, cache = sys.argv[1], Path(sys.argv[2])
    cache.mkdir(parents=True, exist_ok=True)
    if cmd == "fetch":
        fetch(cache)
        return 0
    out = {}
    for a in json.load(open(cache / "top.json")):
        r = run(pickle.load(open(cache / f"{a}.pkl", "rb")), *PERIODS[cmd])
        if r:
            out[a] = r
    json.dump(out, open(cache / f"{cmd}.json", "w"))
    print(f"{'asset':7} {'yrs':>4} {'n':>4} {'win':>5} {'strat':>8} {'mdd':>7} {'hold':>8} {'holdMDD':>8}")
    for a, r in sorted(out.items(), key=lambda kv: -kv[1]["ret"]):
        print(f"{a:7} {r['years']:4.1f} {r['n']:4d} {r['win'] * 100:4.0f}% {r['ret'] * 100:+7.1f}% "
              f"{r['mdd'] * 100:6.1f}% {r['hold'] * 100:+7.1f}% {r['hold_mdd'] * 100:7.1f}%")
    is_ = out if cmd == "is" else json.load(open(cache / "is.json"))
    sel = selected(is_)
    print("selected (in-sample criteria):", sel)
    if cmd == "oos":
        for name, group in (("selected", sel), ("rejected", [a for a in is_ if a not in sel])):
            g = [a for a in group if a in out]
            avg = lambda k: sum(out[a][k] for a in g) / len(g)  # noqa: E731
            print(f"{name:9} strat {avg('ret') * 100:+.1f}%  hold {avg('hold') * 100:+.1f}%  "
                  f"mdd {avg('mdd') * 100:.1f}%  holdMDD {avg('hold_mdd') * 100:.1f}%  "
                  f"beat-hold {sum(out[a]['ret'] > out[a]['hold'] for a in g)}/{len(g)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
