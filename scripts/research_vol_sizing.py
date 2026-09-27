"""Does POSITION SIZING -- not entry/exit selection -- improve the house Donchian 1h rule's
risk-adjusted returns? `strategies/strategy_record.py` runs 13 coins (`sr.ASSETS`) as an
equal-weight portfolio: each coin is its own sleeve funded at 1/13 of capital, trades its FULL
sleeve on every signal (100% in, 100% out), sleeves never rebalanced against each other.
Entries/exits (`close > max HIGH of prior 168 bars` / `close < min LOW of prior 72 bars`) are
NEVER touched here -- sizing cannot change WHETHER a trade fires, only how much of a sleeve (or
of total portfolio capital) is behind it. Because a sleeve trades in-or-out with a fraction `s`
of its own equity, its equity multiplies by (1 + s*r) per trade where r is the trade's FULL-SIZE
net return -- the exact same r the unfiltered house rule realizes -- so every method below
produces bit-identical trade dates/prices to the published baseline, just different capital
behind each one.

Candidate families (few pre-chosen parameter values, no fine grid search):
  invvol     : per-trade size s = clip(target_vol / realized_vol_30d, 0, 1). realized_vol_30d =
               annualized stdev of hourly log returns over the 720 bars (30 days) STRICTLY
               before the entry bar (no lookahead; shift(1) on top of the rolling window so the
               entry bar's own return is excluded too). A coin too young for the full window
               gets s=1 (filter inactive during warm-up, same convention as
               scripts/research_trend_filter.py's trend_ref). target_vol in {30%, 50%, 80%}
               annualized.
  portvol    : portfolio-level vol targeting with a cash buffer. Build the UNSCALED baseline
               portfolio's (equal-weight, full sleeve) DAILY return series for the window, then
               scale day t's return by f_t = clip(target_vol / realized_vol_20d, 0, 1), where
               realized_vol_20d is the trailing 20 trading days of that SAME unscaled series,
               shifted by one day (causal). The unscaled fraction (1 - f_t) of capital sits in
               cash at 0% yield -- deliberately conservative; real stablecoin/T-bill yield would
               only help this variant further. target_vol in {15%, 25%, 40%} annualized.
  riskparity : replace the equal 1/13 initial capital weights with w_i ~ 1/vol_i, where vol_i is
               each coin's OWN realized volatility (annualized stdev of daily log returns) over
               its available IN-SAMPLE history -- computed ONCE, never updated, reused as-is
               out-of-sample. w_i is capped at cap x the equal weight (stops BTC/ETH's low vol
               from swallowing the book) and renormalized to sum to 1 after capping. Per-trade
               sizing is untouched (s=1 always) -- only which SHARE of total capital sits in
               each sleeve changes. cap in {1.5, 2.0, 3.0}.
  9 variants total + the unfiltered/equal-weight baseline = 10 in-sample runs (auditable below).

Pre-registration (fixed BEFORE looking at any 2026-01-01+ number; discipline mirrors
scripts/research_trend_filter.py and scripts/screen_universe.py):
  - In-sample = 2022-01-01..2025-12-31 (as much history as each coin has; SUI/PEPE/WLD list
    later and just start later). Out-of-sample = 2026-01-01..now.
  - Metrics computed on ONE combined hourly PORTFOLIO equity curve (dollar-weighted sum of the
    13 sleeves' mark-to-market equity paths, not an average of per-coin summary stats -- a
    portfolio can diversify away drawdown that a per-coin average would miss). Sleeves for a
    coin not yet listed hold 1.0 (cash, no return) until that coin's first bar.
  - Selection rule (fixed before running): compute in-sample portfolio Calmar (total return /
    |max drawdown|) and average capital deployed (time-weighted fraction of total portfolio
    capital actually in a position, not idle cash) for baseline and all 9 variants. (1) Discard
    any variant whose average capital deployed is < 50% of baseline's -- rules out "de-risking"
    that is just sitting out of the market. (2) Among survivors, keep only variants whose Calmar
    is >= baseline's (must actually raise risk-adjusted return, not just move it around). (3)
    Among those, pick the single highest Calmar; ties -> fewest parameters / most interpretable
    family. If no variant survives both filters, the verdict is "don't adopt" regardless of what
    2026 shows -- OOS is looked at exactly once, after this rule is applied mechanically.

Usage (CACHE = the shared filter_research scratch dir; reuses the pkl cache
scripts/research_trend_filter.py already fetched -- 1h Binance klines since 2022-01-01, same 13
coins as sr.ASSETS; only fetches if a coin's pkl is missing):
  .venv-bots/bin/python scripts/research_vol_sizing.py fetch CACHE   # 1h since 2022-01-01 (skips cached coins)
  .venv-bots/bin/python scripts/research_vol_sizing.py sweep CACHE   # in-sample sweep + mechanical winner pick
  .venv-bots/bin/python scripts/research_vol_sizing.py oos CACHE     # out-of-sample report, winner HARD-CODED below
"""

from __future__ import annotations

import datetime as dt
import pickle
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))
import strategy_record as sr  # noqa: E402

KLINES = "https://api.binance.com/api/v3/klines"
FETCH_START = dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc)

ENTRY_LB = sr.ENTRY_LB     # 168 -- channel_high lookback (breakout)
EXIT_LB = sr.EXIT_LB       # 72  -- channel_low lookback (trailing exit)
FEE = sr.FEE               # 0.001/side
VOL_LB = 720               # 30 days of 1h bars -- per-trade realized-vol lookback
ANN_HOURLY = (24 * 365) ** 0.5
ANN_DAILY = 365 ** 0.5


def _ms(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


IS_START, IS_END = _ms(2022, 1, 1), _ms(2026, 1, 1)
OOS_START, OOS_END = _ms(2026, 1, 1), 10 ** 15
EQUAL_W = {a: 1.0 / len(sr.ASSETS) for a in sr.ASSETS}


# ---------------------------------------------------------------------------
# Data loading (reuses research_trend_filter.py's cache format/layout)

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
        print(a, len(bars), flush=True)


def _load(cache: Path) -> dict[str, dict]:
    out = {}
    for a in sr.ASSETS:
        bars = pickle.load(open(cache / f"{a}.pkl", "rb"))
        out[a] = {
            "ts": np.array([b[0] for b in bars], dtype="int64"),
            "high": np.array([b[1] for b in bars], dtype="float64"),
            "low": np.array([b[2] for b in bars], dtype="float64"),
            "close": np.array([b[3] for b in bars], dtype="float64"),
        }
    return out


def _prep(coin: dict) -> dict:
    """Precompute channel_high / channel_low / trailing realized vol over the coin's FULL cached
    history (genesis to now) -- window boundaries are applied later, purely to the trade-state
    replay, exactly like research_trend_filter.simulate()'s `seg` convention."""
    high = pd.Series(coin["high"])
    low = pd.Series(coin["low"])
    close = pd.Series(coin["close"])
    channel_high = high.rolling(ENTRY_LB).max().shift(1).to_numpy()
    channel_low = low.rolling(EXIT_LB).min().shift(1).to_numpy()
    logret = np.log(close / close.shift(1))
    vol_ann = (logret.rolling(VOL_LB, min_periods=VOL_LB).std().shift(1) * ANN_HOURLY).to_numpy()
    out = dict(coin)
    out["channel_high"] = channel_high
    out["channel_low"] = channel_low
    out["vol_ann"] = vol_ann
    return out


# ---------------------------------------------------------------------------
# Sizing functions: vol_ann (float, NaN if warm-up) -> fraction of sleeve in [0, 1]

SizingFn = Callable[[float], float]


def size_full(_vol_ann: float) -> float:
    return 1.0


def make_size_invvol(target_vol: float) -> SizingFn:
    def f(vol_ann: float) -> float:
        if not np.isfinite(vol_ann) or vol_ann <= 0:
            return 1.0
        return float(min(1.0, target_vol / vol_ann))
    return f


# ---------------------------------------------------------------------------
# Per-coin replay: identical entry/exit bars to sr.step; only the per-trade size `s` -- chosen
# once at entry from the info available at that instant, held for the trade's life -- varies.
# Flat-at-window-start convention matches research_trend_filter.simulate() (bars with
# ts <= start_ms or ts > end_ms are skipped without touching the position state).

def replay(coin: dict, start_ms: int, end_ms: int, sizing_fn: SizingFn) -> dict:
    ts = coin["ts"]
    close = coin["close"]
    ch_hi = coin["channel_high"]
    ch_lo = coin["channel_low"]
    vol = coin["vol_ann"]
    n = len(ts)
    equity = np.ones(n)
    exposure = np.zeros(n)  # fraction of THIS sleeve actually deployed at bar i (0 if flat)
    trades: list[dict] = []
    long_ = False
    entry_price = entry_equity = None
    s = 1.0
    for i in range(ENTRY_LB, n):
        t = ts[i]
        if t <= start_ms or t > end_ms:
            equity[i] = equity[i - 1]
            continue
        if not long_:
            level = ch_hi[i]
            if np.isnan(level):
                equity[i] = equity[i - 1]
                continue
            if close[i] > level:
                long_ = True
                entry_price = close[i]
                entry_equity = equity[i - 1]
                s = sizing_fn(vol[i])
                equity[i] = entry_equity * ((1 - s) + s * (1 - FEE))
                exposure[i] = s
                trades.append({"entry_ts": int(t), "entry_price": float(entry_price), "s": s})
            else:
                equity[i] = equity[i - 1]
        else:
            level = ch_lo[i]
            mtm = entry_equity * ((1 - s) + s * (1 - FEE) * (close[i] / entry_price))
            if not np.isnan(level) and close[i] < level:
                equity[i] = entry_equity * ((1 - s) + s * (1 - FEE) * (close[i] / entry_price) * (1 - FEE))
                exposure[i] = 0.0
                trades[-1]["exit_ts"] = int(t)
                trades[-1]["exit_price"] = float(close[i])
                trades[-1]["r"] = float((close[i] / entry_price) * (1 - FEE) ** 2 - 1)
                long_ = False
            else:
                equity[i] = mtm
                exposure[i] = s
    if long_:
        trades[-1]["exit_ts"] = None  # still open at window end -- mark-to-market only
    return {"ts": ts, "equity": equity, "exposure": exposure, "trades": trades}


# ---------------------------------------------------------------------------
# Portfolio assembly: dollar-weighted sum of sleeve equity paths on a common hourly grid.
# A sleeve not yet listed holds 1.0 (cash, no return) until its own first bar.

def portfolio(coins: dict[str, dict], start_ms: int, end_ms: int, sizing_fn: SizingFn,
              weights: dict[str, float]) -> dict:
    per_coin_eq, per_coin_exp, per_coin_trades = {}, {}, {}
    for a, coin in coins.items():
        r = replay(coin, start_ms, end_ms, sizing_fn)
        idx = pd.to_datetime(r["ts"], unit="ms", utc=True)
        per_coin_eq[a] = pd.Series(r["equity"], index=idx)
        per_coin_exp[a] = pd.Series(r["exposure"], index=idx)
        per_coin_trades[a] = r["trades"]
    master_idx = per_coin_eq[next(iter(per_coin_eq))].index
    for s in list(per_coin_eq.values())[1:]:
        master_idx = master_idx.union(s.index)
    eq_df = pd.DataFrame({a: s.reindex(master_idx).ffill().fillna(1.0) for a, s in per_coin_eq.items()})
    exp_df = pd.DataFrame({a: s.reindex(master_idx).ffill().fillna(0.0) for a, s in per_coin_exp.items()})
    w = pd.Series(weights)
    port_eq = (eq_df * w).sum(axis=1)
    port_exp = (exp_df * w).sum(axis=1)
    idx_ms = master_idx.tz_convert("UTC").tz_localize(None).astype("datetime64[ms]").view("int64")
    in_window = (idx_ms > start_ms) & (idx_ms <= end_ms)
    # Trim the reported equity curve to the window too (plus one anchor bar just before it,
    # value 1.0 by construction) -- otherwise CAGR/day-count would stretch back to each coin's
    # own genesis (or forward to "now"), since master_idx spans every coin's full cached history
    # regardless of `start_ms`/`end_ms`.
    keep = in_window.copy()
    first = np.argmax(in_window) if in_window.any() else 0
    if in_window.any() and first > 0:
        keep[first - 1] = True
    return {"equity": port_eq[keep], "exposure": port_exp[in_window], "trades": per_coin_trades}


def buyhold_portfolio(coins: dict[str, dict], start_ms: int, end_ms: int,
                       weights: dict[str, float]) -> pd.Series:
    series = {}
    for a, coin in coins.items():
        ts, close = coin["ts"], coin["close"]
        mask = (ts > start_ms) & (ts <= end_ms)
        if not mask.any():
            continue
        first_i = np.argmax(mask)
        s = pd.Series(1.0, index=pd.to_datetime(ts, unit="ms", utc=True))
        s.iloc[first_i:] = close[first_i:] / close[first_i]
        series[a] = s
    master_idx = series[next(iter(series))].index
    for s in list(series.values())[1:]:
        master_idx = master_idx.union(s.index)
    df = pd.DataFrame({a: s.reindex(master_idx).ffill().fillna(1.0) for a, s in series.items()})
    w = pd.Series(weights)
    port = (df * w).sum(axis=1)
    idx_ms = master_idx.tz_convert("UTC").tz_localize(None).astype("datetime64[ms]").view("int64")
    in_window = (idx_ms > start_ms) & (idx_ms <= end_ms)
    keep = in_window.copy()
    first = np.argmax(in_window) if in_window.any() else 0
    if in_window.any() and first > 0:
        keep[first - 1] = True
    return port[keep]


# ---------------------------------------------------------------------------
# Stats on one combined hourly portfolio equity curve.

def _cagr(eq: pd.Series) -> float:
    days = (eq.index[-1] - eq.index[0]).total_seconds() / 86400
    if days <= 0:
        return 0.0
    return float((eq.iloc[-1] / eq.iloc[0]) ** (365.25 / days) - 1)


def _maxdd(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def _worst_month(eq: pd.Series) -> float:
    monthly = eq.resample("ME").last().dropna()
    rets = monthly.pct_change().dropna()
    return float(rets.min()) if len(rets) else 0.0


def stats(eq: pd.Series, exposure: pd.Series | None = None) -> dict:
    total_ret = float(eq.iloc[-1] / eq.iloc[0] - 1)
    mdd = _maxdd(eq)
    cagr = _cagr(eq)
    calmar = cagr / abs(mdd) if mdd != 0 else float("inf")
    avg_dep = float(exposure.mean()) if exposure is not None and len(exposure) else float("nan")
    ret_per_exposure = total_ret / avg_dep if avg_dep else float("nan")
    return {"ret": total_ret, "cagr": cagr, "mdd": mdd, "calmar": calmar,
            "worst_month": _worst_month(eq), "avg_deployed": avg_dep,
            "ret_per_exposure": ret_per_exposure}


# ---------------------------------------------------------------------------
# riskparity: static weights from in-sample (2022-2025) per-coin realized vol.

def risk_parity_weights(coins: dict[str, dict], cap_mult: float) -> dict[str, float]:
    inv_vol = {}
    for a, coin in coins.items():
        ts, close = coin["ts"], coin["close"]
        mask = (ts > IS_START) & (ts <= IS_END)
        c = close[mask]
        if len(c) < 30:
            inv_vol[a] = 1.0 / len(sr.ASSETS)
            continue
        daily = pd.Series(c, index=pd.to_datetime(ts[mask], unit="ms", utc=True)).resample("D").last().dropna()
        logret = np.log(daily / daily.shift(1)).dropna()
        vol = float(logret.std() * ANN_DAILY)
        inv_vol[a] = 1.0 / vol if vol > 0 else 1.0 / len(sr.ASSETS)
    total = sum(inv_vol.values())
    w = {a: v / total for a, v in inv_vol.items()}
    equal = 1.0 / len(sr.ASSETS)
    cap = equal * cap_mult
    capped = {a: min(v, cap) for a, v in w.items()}
    total2 = sum(capped.values())
    return {a: v / total2 for a, v in capped.items()}


# ---------------------------------------------------------------------------
# portvol: portfolio-level daily vol-targeting overlay on top of an already-built baseline path.

def portvol_overlay(baseline_eq: pd.Series, target_vol: float, lb_days: int = 20) -> tuple[pd.Series, float]:
    daily = baseline_eq.resample("D").last().dropna()
    ret = daily.pct_change().dropna()
    vol = ret.rolling(lb_days, min_periods=lb_days).std().shift(1) * ANN_DAILY
    f = (target_vol / vol).clip(upper=1.0)
    f = f.fillna(1.0)
    scaled_ret = ret * f
    eq = (1 + scaled_ret).cumprod()
    eq = pd.concat([pd.Series([1.0], index=[daily.index[0]]), eq])
    return eq, float(f.mean())


# ---------------------------------------------------------------------------
VARIANTS = {
    "invvol_30pct": {"family": "invvol", "target_vol": 0.30},
    "invvol_50pct": {"family": "invvol", "target_vol": 0.50},
    "invvol_80pct": {"family": "invvol", "target_vol": 0.80},
    "portvol_15pct": {"family": "portvol", "target_vol": 0.15},
    "portvol_25pct": {"family": "portvol", "target_vol": 0.25},
    "portvol_40pct": {"family": "portvol", "target_vol": 0.40},
    "riskparity_cap1.5x": {"family": "riskparity", "cap": 1.5},
    "riskparity_cap2.0x": {"family": "riskparity", "cap": 2.0},
    "riskparity_cap3.0x": {"family": "riskparity", "cap": 3.0},
}

# Pre-registered winner -- fixed AFTER running `sweep` on in-sample data (2022-01-01..2025-12-31)
# and BEFORE looking at any 2026 number. See STRATEGY_LEADERBOARD.md 2026-09-27 "position sizing"
# section for the full sweep table and the mechanical application of the selection rule above.
WINNER: str | None = "invvol_50pct"  # sweep() output: invvol_50pct/80pct and portvol_25pct/40pct
# clear both bars (invvol_30pct has the single highest in-sample Calmar, 1.69, but fails the
# capital-deployed floor: 12.1% vs the 14.6% (=50% of baseline's 29.2%) minimum -- exactly the
# "de-risking by sitting in cash" failure mode the rule exists to catch). Among survivors,
# invvol_50pct has the highest in-sample Calmar (1.48 vs baseline 0.97) -- see
# STRATEGY_LEADERBOARD.md for the full sweep table.


def _run_variant(coins: dict[str, dict], name: str, spec: dict, start_ms: int, end_ms: int,
                  rp_cache: dict[float, dict[str, float]]) -> dict:
    if name == "baseline":
        p = portfolio(coins, start_ms, end_ms, size_full, EQUAL_W)
        return {"equity": p["equity"], "exposure": p["exposure"]}
    fam = spec["family"]
    if fam == "invvol":
        fn = make_size_invvol(spec["target_vol"])
        p = portfolio(coins, start_ms, end_ms, fn, EQUAL_W)
        return {"equity": p["equity"], "exposure": p["exposure"]}
    if fam == "riskparity":
        cap = spec["cap"]
        if cap not in rp_cache:
            rp_cache[cap] = risk_parity_weights(coins, cap)
        p = portfolio(coins, start_ms, end_ms, size_full, rp_cache[cap])
        return {"equity": p["equity"], "exposure": p["exposure"]}
    if fam == "portvol":
        base = _run_variant(coins, "baseline", {}, start_ms, end_ms, rp_cache)
        eq, avg_f = portvol_overlay(base["equity"], spec["target_vol"])
        base_exp_daily = base["exposure"].resample("D").mean()
        avg_dep = float((base_exp_daily.reindex(eq.index[1:]).ffill() * avg_f).mean())
        return {"equity": eq, "exposure": None, "avg_deployed_override": avg_dep}
    raise ValueError(fam)


def _stats_for(result: dict) -> dict:
    if "avg_deployed_override" in result:
        st = stats(result["equity"], None)
        st["avg_deployed"] = result["avg_deployed_override"]
        st["ret_per_exposure"] = st["ret"] / st["avg_deployed"] if st["avg_deployed"] else float("nan")
        return st
    return stats(result["equity"], result["exposure"])


def sweep(cache: Path) -> int:
    coins_raw = _load(cache)
    coins = {a: _prep(c) for a, c in coins_raw.items()}
    rp_cache: dict[float, dict[str, float]] = {}

    rows = {}
    base_result = _run_variant(coins, "baseline", {}, IS_START, IS_END, rp_cache)
    rows["baseline"] = _stats_for(base_result)
    for name, spec in VARIANTS.items():
        result = _run_variant(coins, name, spec, IS_START, IS_END, rp_cache)
        rows[name] = _stats_for(result)

    print("in-sample 2022-01-01..2025-12-31 -- ONE combined portfolio equity curve per variant\n")
    header = f"{'variant':20} {'totalRet':>10} {'CAGR':>8} {'maxDD':>8} {'Calmar':>8} {'avgDeployed':>11} {'retPerExp':>10}"
    print(header)
    for name, st in rows.items():
        print(f"{name:20} {st['ret'] * 100:9.1f}% {st['cagr'] * 100:7.1f}% {st['mdd'] * 100:7.1f}% "
              f"{st['calmar']:8.2f} {st['avg_deployed'] * 100:10.1f}% {st['ret_per_exposure'] * 100:9.1f}%")

    base = rows["baseline"]
    print(f"\n{len(VARIANTS)} variants tried (+ baseline) across 3 families "
          f"(invvol x3, portvol x3, riskparity x3).")
    print(f"baseline avg capital deployed: {base['avg_deployed'] * 100:.1f}%  (50% floor: "
          f"{base['avg_deployed'] * 50:.1f}%); baseline Calmar: {base['calmar']:.2f}\n")
    print("selection rule applied mechanically:")
    survivors = []
    for name, st in rows.items():
        if name == "baseline":
            continue
        dep_ok = st["avg_deployed"] >= 0.5 * base["avg_deployed"]
        calmar_ok = st["calmar"] >= base["calmar"]
        print(f"  {name:20} avgDeployed>=50%base: {dep_ok!s:5}  Calmar>=base: {calmar_ok!s:5}  "
              f"(Calmar {st['calmar']:.2f} vs {base['calmar']:.2f})")
        if dep_ok and calmar_ok:
            survivors.append(name)
    if survivors:
        winner = max(survivors, key=lambda n: rows[n]["calmar"])
        print(f"\nWINNER (pre-registered mechanical pick): {winner}  {VARIANTS[winner]}")
    else:
        print("\nNo variant clears both filters -- pre-registered verdict is DON'T ADOPT, "
              "no OOS number can override this.")
    return 0


def _per_year_table(coins: dict[str, dict], variant_name: str, spec: dict,
                     rp_cache: dict[float, dict[str, float]]) -> list[tuple[int, float, float, float]]:
    out = []
    for year in range(2022, 2027):
        a, b = _ms(year, 1, 1), _ms(year + 1, 1, 1)
        try:
            base_r = _run_variant(coins, "baseline", {}, a, b, rp_cache)
            var_r = _run_variant(coins, variant_name, spec, a, b, rp_cache)
            hold_eq = buyhold_portfolio(coins, a, b, EQUAL_W)
        except Exception:
            continue
        base_st = _stats_for(base_r)
        var_st = _stats_for(var_r)
        hold_ret = float(hold_eq.iloc[-1] / hold_eq.iloc[0] - 1)
        out.append((year, base_st["ret"], var_st["ret"], hold_ret))
    return out


def oos(cache: Path) -> int:
    if WINNER is None or WINNER == "PLACEHOLDER":
        print("WINNER not set -- run `sweep` first and hard-code the mechanical pick.", file=sys.stderr)
        return 1
    coins_raw = _load(cache)
    coins = {a: _prep(c) for a, c in coins_raw.items()}
    rp_cache: dict[float, dict[str, float]] = {}
    spec = VARIANTS[WINNER]

    base_r = _run_variant(coins, "baseline", {}, OOS_START, OOS_END, rp_cache)
    var_r = _run_variant(coins, WINNER, spec, OOS_START, OOS_END, rp_cache)
    hold_eq = buyhold_portfolio(coins, OOS_START, OOS_END, EQUAL_W)

    base_st = _stats_for(base_r)
    var_st = _stats_for(var_r)
    hold_st = stats(hold_eq, None)

    print(f"out-of-sample 2026-01-01..now -- winner = {WINNER}  {spec}\n")
    header = f"{'':10} {'totalRet':>10} {'CAGR':>8} {'maxDD':>8} {'Calmar':>8} {'worstMo':>8} {'avgDeployed':>11} {'retPerExp':>10}"
    print(header)
    for label, st in (("baseline", base_st), (WINNER, var_st), ("buy&hold", hold_st)):
        print(f"{label:10} {st['ret'] * 100:9.1f}% {st['cagr'] * 100:7.1f}% {st['mdd'] * 100:7.1f}% "
              f"{st['calmar']:8.2f} {st['worst_month'] * 100:7.1f}% {st['avg_deployed'] * 100:10.1f}% "
              f"{st['ret_per_exposure'] * 100:9.1f}%")

    print("\nper-year breakdown (portfolio total return, flat-start each calendar year):")
    print(f"{'year':6} {'baseline':>10} {WINNER:>16} {'buy&hold':>10}")
    for year, br, vr, hr in _per_year_table(coins, WINNER, spec, rp_cache):
        print(f"{year:<6} {br * 100:9.1f}% {vr * 100:15.1f}% {hr * 100:9.1f}%")

    aug_start, aug_end = pd.Timestamp("2026-08-01", tz="UTC"), pd.Timestamp("2026-09-01", tz="UTC")
    base_aug = base_r["equity"].loc[aug_start:aug_end]
    var_aug = var_r["equity"].loc[aug_start:aug_end]
    print(f"\nAug-2026 rally check (entries/exits are identical across all sizing variants by "
          f"construction -- sizing never gates the signal): "
          f"baseline portfolio return over Aug 2026: {(base_aug.iloc[-1] / base_aug.iloc[0] - 1) * 100:.1f}%, "
          f"{WINNER}: {(var_aug.iloc[-1] / var_aug.iloc[0] - 1) * 100:.1f}%.")
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
    print("usage: research_vol_sizing.py {fetch|sweep|oos} CACHE", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
