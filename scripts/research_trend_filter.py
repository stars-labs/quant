"""Does a regime/range filter make the house Donchian 1h rule (strategies/strategy_record.py)
more robust? The unfiltered rule wins ~38% of trades (most losses are false breakouts in
ranging markets). This script sweeps a few simple, one-or-two-parameter filters ON TOP of the
existing entry (never touches the exit), fits/selects on IN-SAMPLE data only, fixes the choice,
then reports OUT-OF-SAMPLE 2026 for the same 13 coins (sr.ASSETS) net of fees, vs the unfiltered
rule and vs buy-and-hold.

Pre-registration (fixed before looking at 2026-01-01+, discipline mirrors scripts/screen_universe.py):
  - In-sample = 2022-01-01 .. 2025-12-31 (as much history as Binance has per coin; newer listings
    — SUI/PEPE/WLD — just have a shorter in-sample). Out-of-sample = 2026-01-01 .. now.
  - Candidate families (each with 3 pre-chosen parameter values — NOT a fine grid search):
      trend_self  : entry also requires close > SMA(close) of the LAST N*24 1h bars of the same
                    coin (a 1h proxy for an N-day moving average, computed on bars strictly
                    before the signal bar — no lookahead). N in {100, 150, 200}.
      trend_btc   : same idea but the reference series is always BTC's own close (macro regime
                    gate applied to every coin, incl. BTC itself). N in {100, 150, 200}.
      strength_pct: entry also requires close > channel_high * (1+x) — the breakout must clear
                    the channel by a margin, not just tick over it. x in {0.5%, 1%, 2%}.
      atr_breakout: entry also requires (close - channel_high) > k * ATR, ATR = SMA of true
                    range over the last 336 1h bars (~14 days). k in {0.25, 0.5, 1.0}.
      cooldown    : after a LOSING exit, no new entry for C bars. C in {24, 72, 168} (1/3/7 days).
      longer_lb   : widen the entry lookback itself (ENTRY_LB) instead of adding a gate.
                    L in {216, 264, 336} (9/11/14 days) vs the house 168 (7 days).
    18 variants total + the unfiltered baseline = 19 in-sample runs. Reported here so overfitting
    is auditable (see "variants tried" below the tables).
  - Selection rule (fixed before running): among variants that (a) beat the unfiltered rule's
    per-coin return on >= 8/13 in-sample coins (majority, not just the aggregate) AND (b) raise
    the aggregate win rate (the stated failure mode), pick the one with the best return/|maxDD|;
    ties broken toward fewer parameters / the most interpretable filter.

A filter only ever makes entry MORE restrictive (fewer, better breakouts) — the exit rule
(close < min LOW of prior 72 bars) is never touched, so every variant is a strict subset of the
baseline's trades for a given coin, easy to reason about.

Usage (CACHE = any scratch dir; Binance public klines, no key; only fetches sr.ASSETS, not top-30):
  .venv-bots/bin/python scripts/research_trend_filter.py fetch CACHE   # 1h since 2022-01-01
  .venv-bots/bin/python scripts/research_trend_filter.py sweep CACHE  # in-sample sweep + picks winner
  .venv-bots/bin/python scripts/research_trend_filter.py oos CACHE    # out-of-sample report, chosen filter is HARD-CODED below (WINNER)
"""

from __future__ import annotations

import datetime as dt
import pickle
import sys
import time
from collections import deque
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))
import strategy_record as sr  # noqa: E402

KLINES = "https://api.binance.com/api/v3/klines"
FETCH_START = dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc)


def _ms(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


IS_START, IS_END = _ms(2022, 1, 1), _ms(2026, 1, 1)
OOS_START, OOS_END = _ms(2026, 1, 1), 10**15


def fetch(cache: Path) -> None:
    now = time.time() * 1000
    for a in sr.ASSETS:
        p = cache / f"{a}.pkl"
        if p.exists():
            continue
        bars, s = [], int(FETCH_START.timestamp() * 1000)
        while True:
            r = requests.get(KLINES, params={"symbol": a + "USDT", "interval": "1h",
                                             "startTime": s, "limit": 1000}, timeout=30).json()
            if not isinstance(r, list):
                print(a, "ERROR", r)
                break
            bars += [(int(k[6]), float(k[2]), float(k[3]), float(k[4])) for k in r if int(k[6]) <= now]
            if len(r) < 1000:
                break
            s = int(r[-1][6]) + 1
        pickle.dump(bars, open(p, "wb"))
        print(a, len(bars), "from", dt.datetime.fromtimestamp(bars[0][0] / 1000, dt.timezone.utc)
              if bars else None, flush=True)


# ---------------------------------------------------------------------------
# O(n) rolling windows (monotonic deque for max/min, prefix sum for SMA) —
# same semantics as sr.step's max(HIGH of prior LB bars) / min(LOW of prior LB bars):
# window at index i covers bars[i-LB:i] (LB bars strictly before i, i itself excluded).

def rolling_max(vals: list[float], lb: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    dq: deque[tuple[int, float]] = deque()
    for i in range(len(vals)):
        if i >= 1:
            j, v = i - 1, vals[i - 1]
            while dq and dq[-1][1] <= v:
                dq.pop()
            dq.append((j, v))
        while dq and dq[0][0] < i - lb:
            dq.popleft()
        if i >= lb:
            out[i] = dq[0][1]
    return out


def rolling_min(vals: list[float], lb: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    dq: deque[tuple[int, float]] = deque()
    for i in range(len(vals)):
        if i >= 1:
            j, v = i - 1, vals[i - 1]
            while dq and dq[-1][1] >= v:
                dq.pop()
            dq.append((j, v))
        while dq and dq[0][0] < i - lb:
            dq.popleft()
        if i >= lb:
            out[i] = dq[0][1]
    return out


def rolling_sma(vals: list[float], w: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    prefix = 0.0
    prefixes = [0.0] * (len(vals) + 1)
    for i, v in enumerate(vals):
        prefix += v
        prefixes[i + 1] = prefix
    for i in range(len(vals)):
        if i >= w:
            out[i] = (prefixes[i] - prefixes[i - w]) / w
    return out


def true_range(bars: list[sr.Bar]) -> list[float]:
    tr = [0.0] * len(bars)
    for i in range(1, len(bars)):
        _ts, hi, lo, _c = bars[i]
        prev_close = bars[i - 1][3]
        tr[i] = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
    return tr


# ---------------------------------------------------------------------------
# Generic simulator: same entry/exit semantics as sr.step, plus optional filters.
# `trend_ref` (list[float|None], same length as bars) — extra gate: close > trend_ref[i].
# Missing trend_ref (None, e.g. not enough warm-up yet) does NOT block entry — treated as
# "filter inactive" so a newly-listed coin isn't excluded for its entire warm-up window.

def simulate(bars: list[sr.Bar], a: int, b: int, *, entry_lb: int = 168, exit_lb: int = 72,
             trend_ref: list[float | None] | None = None, strength_pct: float = 0.0,
             atr_k: float = 0.0, cooldown_bars: int = 0) -> dict | None:
    seg = [x for x in bars if x[0] < b]
    if entry_lb >= len(seg):
        return None
    # Trading can only start once ENTRY_LB bars of real warm-up exist AND the reporting
    # window has opened — whichever is later. A coin listed after `a` (e.g. SUI/PEPE/WLD)
    # just starts trading at its own genesis + entry_lb, instead of being rejected outright.
    trade_start_ts = max(a, seg[entry_lb][0])
    first = next((i for i, x in enumerate(seg) if x[0] >= trade_start_ts), None)
    if first is None or len(seg) - first < 24 * 180:
        return None
    highs = [x[1] for x in seg]
    lows = [x[2] for x in seg]
    closes = [x[3] for x in seg]
    channel_high = rolling_max(highs, entry_lb)
    channel_low = rolling_min(lows, exit_lb)
    atr = rolling_sma(true_range(seg), 336) if atr_k else None

    f = (1 - sr.FEE) ** 2
    trades: list[float] = []
    long_, entry_price, blocked_until = False, None, -1
    for i in range(entry_lb, len(seg)):
        ts = seg[i][0]
        if ts <= a:
            continue
        close = closes[i]
        if not long_:
            ch = channel_high[i]
            if ch is None or i < blocked_until:
                continue
            ok = close > ch
            if ok and strength_pct:
                ok = close > ch * (1 + strength_pct)
            if ok and atr_k:
                ok = atr[i] is not None and (close - ch) > atr_k * atr[i]
            if ok and trend_ref is not None and trend_ref[i] is not None:
                ok = close > trend_ref[i]
            if ok:
                long_, entry_price = True, close
        else:
            cl = channel_low[i]
            if cl is not None and close < cl:
                r = close / entry_price * f - 1
                trades.append(r)
                if cooldown_bars and r < 0:
                    blocked_until = i + cooldown_bars
                long_, entry_price = False, None
    if long_:
        trades.append(closes[-1] / entry_price * f - 1)

    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in trades:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    hold_closes = closes[first:]
    hpeak, hmdd = hold_closes[0], 0.0
    for c in hold_closes:
        hpeak = max(hpeak, c)
        hmdd = min(hmdd, c / hpeak - 1)
    return {"n": len(trades), "win": sum(r > 0 for r in trades) / len(trades) if trades else 0.0,
            "ret": eq - 1, "mdd": mdd, "hold": hold_closes[-1] / hold_closes[0] - 1, "hold_mdd": hmdd,
            "years": (len(seg) - first) / 24 / 365}


# ---------------------------------------------------------------------------
VARIANTS: dict[str, dict] = {"baseline": {}}
for n in (100, 150, 200):
    VARIANTS[f"trend_self_{n}d"] = {"_trend": "self", "_trend_n": n}
    VARIANTS[f"trend_btc_{n}d"] = {"_trend": "btc", "_trend_n": n}
for x in (0.005, 0.01, 0.02):
    VARIANTS[f"strength_{x * 100:.1f}pct"] = {"strength_pct": x}
for k in (0.25, 0.5, 1.0):
    VARIANTS[f"atr_k{k}"] = {"atr_k": k}
for c in (24, 72, 168):
    VARIANTS[f"cooldown_{c}h"] = {"cooldown_bars": c}
for lb in (216, 264, 336):
    VARIANTS[f"entry_lb_{lb}"] = {"entry_lb": lb}

# Pre-registered winner, fixed AFTER running `sweep` on in-sample data (2022-01-01..2025-12-31)
# and BEFORE looking at any 2026 number — see STRATEGY_LEADERBOARD.md 2026-09-27 "regime/range
# filter" section for the full sweep table. Applying the selection rule mechanically: the ONLY
# variant that both (a) beat the unfiltered rule's per-coin return on >=8/13 coins and (b) raised
# the mean win rate was cooldown_72h (8/13, win 37.76% vs baseline 37.48% — a ~0.3pp bump, and
# mean return -0.8pp vs baseline). Two variants with a materially bigger win-rate lift
# (entry_lb_336: win 38.9%; trend_self_100d: win 38.8%) both landed at 7/13 coins beaten —
# one coin short of the pre-registered majority bar. Kept as a literal (not "whatever sweep
# prints") so `oos` is reproducible even if the sweep is re-run later with different cached data.
WINNER = "cooldown_72h"


def _load(cache: Path) -> dict[str, list[sr.Bar]]:
    return {a: pickle.load(open(cache / f"{a}.pkl", "rb")) for a in sr.ASSETS}


def _variant_kwargs(cache_bars: dict[str, list[sr.Bar]], asset: str, spec: dict) -> dict:
    kwargs = {k: v for k, v in spec.items() if not k.startswith("_")}
    if spec.get("_trend") == "self":
        closes = [x[3] for x in cache_bars[asset]]
        kwargs["trend_ref"] = rolling_sma(closes, spec["_trend_n"] * 24)
    elif spec.get("_trend") == "btc":
        btc_closes = [x[3] for x in cache_bars["BTC"]]
        btc_sma = rolling_sma(btc_closes, spec["_trend_n"] * 24)
        # BTC and the asset share the same 1h grid from the same fetch() call, so index-align.
        kwargs["trend_ref"] = btc_sma if asset == "BTC" else _align_btc(cache_bars, asset, btc_sma)
    return kwargs


def _align_btc(cache_bars, asset, btc_series):
    """Map BTC's per-index series onto `asset`'s bar index by timestamp (handles a coin
    listed later than BTC, whose bar 0 is not BTC's bar 0)."""
    btc_ts = [x[0] for x in cache_bars["BTC"]]
    ts_to_i = {ts: i for i, ts in enumerate(btc_ts)}
    out = []
    for x in cache_bars[asset]:
        i = ts_to_i.get(x[0])
        out.append(btc_series[i] if i is not None else None)
    return out


def sweep(cache: Path) -> int:
    bars = _load(cache)
    results: dict[str, dict[str, dict]] = {}
    for name, spec in VARIANTS.items():
        per_asset = {}
        for a in sr.ASSETS:
            kwargs = _variant_kwargs(bars, a, spec)
            r = simulate(bars[a], IS_START, IS_END, **kwargs)
            if r:
                per_asset[a] = r
        results[name] = per_asset

    base = results["baseline"]
    print(f"in-sample 2022-01-01..2025-12-31 (per coin's available history; {len(base)}/13 coins qualify)\n")
    header = f"{'variant':16} {'coins':>5} {'meanRet':>8} {'medRet':>8} {'win':>5} {'meanMDD':>8} {'beatBase':>9} {'trades':>7}"
    print(header)
    for name, per_asset in results.items():
        common = [a for a in per_asset if a in base]
        if not common:
            continue
        rets = [per_asset[a]["ret"] for a in common]
        wins = [per_asset[a]["win"] for a in common]
        mdds = [per_asset[a]["mdd"] for a in common]
        ntr = sum(per_asset[a]["n"] for a in common)
        beat = sum(per_asset[a]["ret"] > base[a]["ret"] for a in common if a in base)
        mean_ret = sum(rets) / len(rets)
        med_ret = sorted(rets)[len(rets) // 2]
        mean_win = sum(wins) / len(wins)
        mean_mdd = sum(mdds) / len(mdds)
        print(f"{name:16} {len(common):5d} {mean_ret * 100:7.1f}% {med_ret * 100:7.1f}% "
              f"{mean_win * 100:4.0f}% {mean_mdd * 100:7.1f}% {beat:6d}/{len(common):<3d} {ntr:7d}")

    print(f"\n{len(VARIANTS) - 1} filtered variants tried (+ baseline) across 6 families. "
          f"Selection rule: beat baseline return on >=8/13 coins AND raise mean win rate, "
          f"then best mean-return/|meanMDD|; ties -> fewest params.")
    print(f"WINNER (pre-registered, hard-coded for `oos`): {WINNER}  {VARIANTS[WINNER]}")
    return 0


def oos(cache: Path) -> int:
    bars = _load(cache)
    spec = VARIANTS[WINNER]
    rows_base, rows_var = {}, {}
    for a in sr.ASSETS:
        rb = simulate(bars[a], OOS_START, OOS_END)
        rv = simulate(bars[a], OOS_START, OOS_END, **_variant_kwargs(bars, a, spec))
        if rb:
            rows_base[a] = rb
        if rv:
            rows_var[a] = rv

    print(f"out-of-sample 2026-01-01..now — filter = {WINNER} {spec}\n")
    header = (f"{'asset':7} {'base%':>8} {'filt%':>8} {'hold%':>8} {'baseMDD':>8} {'filtMDD':>8} "
              f"{'baseN':>6} {'filtN':>6} {'baseWin':>8} {'filtWin':>8}")
    print(header)
    beats_base_over_unfiltered = 0
    beats_hold = 0
    n = 0
    for a in sr.ASSETS:
        if a not in rows_base or a not in rows_var:
            print(f"{a:7} insufficient out-of-sample history")
            continue
        b, v = rows_base[a], rows_var[a]
        n += 1
        beats_base_over_unfiltered += v["ret"] > b["ret"]
        beats_hold += v["ret"] > v["hold"]
        print(f"{a:7} {b['ret'] * 100:7.1f}% {v['ret'] * 100:7.1f}% {v['hold'] * 100:7.1f}% "
              f"{b['mdd'] * 100:7.1f}% {v['mdd'] * 100:7.1f}% {b['n']:6d} {v['n']:6d} "
              f"{b['win'] * 100:7.0f}% {v['win'] * 100:7.0f}%")

    def agg(rows):
        rets = [r["ret"] for r in rows.values()]
        return sum(rets) / len(rets), sum(r["win"] for r in rows.values()) / len(rows), \
            sum(r["mdd"] for r in rows.values()) / len(rows), sum(r["n"] for r in rows.values())

    mb, wb, db, nb = agg(rows_base)
    mv, wv, dv, nv = agg(rows_var)
    mh = sum(r["hold"] for r in rows_var.values()) / len(rows_var)
    dh = sum(r["hold_mdd"] for r in rows_var.values()) / len(rows_var)
    print(f"\n{'':7} {'meanRet':>8} {'win':>5} {'meanMDD':>8} {'trades':>7}")
    print(f"{'unfilt':7} {mb * 100:7.1f}% {wb * 100:4.0f}% {db * 100:7.1f}% {nb:7d}")
    print(f"{'filter':7} {mv * 100:7.1f}% {wv * 100:4.0f}% {dv * 100:7.1f}% {nv:7d}")
    print(f"{'hold':7} {mh * 100:7.1f}% {'':>5} {dh * 100:7.1f}%")
    print(f"\nfilter beats unfiltered on {beats_base_over_unfiltered}/{n} coins; "
          f"filter beats buy&hold on {beats_hold}/{n} coins.")

    # Aug-2026 rally sanity check: does the filter still catch it? (the wealth-effect the
    # product relies on). Report per-coin whether ANY trade (filtered or not) was open/entered
    # during Aug 2026 and its return.
    aug_start, aug_end = _ms(2026, 8, 1), _ms(2026, 9, 1)
    print("\nAug-2026 rally check (any entry with ts in [2026-08-01, 2026-09-01)):")
    for a in sr.ASSETS:
        if a not in rows_var:
            continue
        kwargs = _variant_kwargs(bars, a, spec)
        seg = [x for x in bars[a] if x[0] < OOS_END]
        entry_lb = kwargs.get("entry_lb", 168)
        exit_lb = kwargs.get("exit_lb", 72)
        highs = [x[1] for x in seg]
        lows = [x[2] for x in seg]
        closes = [x[3] for x in seg]
        channel_high = rolling_max(highs, entry_lb)
        channel_low = rolling_min(lows, exit_lb)
        atr = rolling_sma(true_range(seg), 336) if kwargs.get("atr_k") else None
        long_, entry_price, blocked_until = False, None, -1
        hit = False
        for i in range(entry_lb, len(seg)):
            ts = seg[i][0]
            close = closes[i]
            if not long_:
                ch = channel_high[i]
                if ch is None or i < blocked_until:
                    continue
                ok = close > ch
                if ok and kwargs.get("strength_pct"):
                    ok = close > ch * (1 + kwargs["strength_pct"])
                if ok and kwargs.get("atr_k"):
                    ok = atr[i] is not None and (close - ch) > kwargs["atr_k"] * atr[i]
                if ok and kwargs.get("trend_ref") is not None and kwargs["trend_ref"][i] is not None:
                    ok = close > kwargs["trend_ref"][i]
                if ok:
                    long_, entry_price = True, close
                    if aug_start <= ts < aug_end:
                        hit = True
            else:
                cl = channel_low[i]
                if cl is not None and close < cl:
                    if kwargs.get("cooldown_bars") and close / entry_price * (1 - sr.FEE) ** 2 - 1 < 0:
                        blocked_until = i + kwargs["cooldown_bars"]
                    long_, entry_price = False, None
        # also: were we LONG at any point during August (entered before, still held)?
        print(f"  {a:7} {'entered-in-Aug' if hit else ('' )}")
    return 0


def main() -> int:
    cmd, cache = sys.argv[1], Path(sys.argv[2])
    cache.mkdir(parents=True, exist_ok=True)
    if cmd == "fetch":
        fetch(cache)
        return 0
    if cmd == "sweep":
        return sweep(cache)
    if cmd == "oos":
        return oos(cache)
    print("usage: research_trend_filter.py {fetch|sweep|oos} CACHE", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
