"""Can the opportunity radar call a DAILY breakout a "buy trigger" on US equities / commodities?

Question: the crypto radar (/scan, migration 035) shows "distance to the buy trigger" because
the house 1h Donchian rule was screened out of sample (screen_universe.py). Before the equity /
commodity sections (migration 036) use the same trigger language, the exact daily rule must
earn it with the same discipline. If it does not, those sections show observations only.

Data (daily closes, the same feeds the live scan uses):
  equities    Yahoo 15y daily via findata.closes_yahoo (split-adjusted, NOT dividend-adjusted —
              both legs miss dividends, so the comparison is fair but absolute returns understate)
  commodities findata.net continuous futures via findata.closes_commodity (budget-guarded; the
              fetch step costs ~10 requests per symbol once, then the on-disk cache serves it).
              Continuous front-month series are NOT roll-adjusted: roll gaps hit buy-and-hold and
              the strategy alike, and neither is exactly an investable return.
Universe: the live scan's — SPY/QQQ/IWM/SMH, 8 mega caps, the /semis NVDA supply chain
(nautilus_equity/semi_analysis.py UNIVERSE) and the 12 /commodities futures. The semis list was
drawn up in 2026 with hindsight (AI winners): survivorship bias flatters buy-and-hold AND the
long-only rule; only the strategy-vs-hold comparison is meaningful.

Rules (long-only, decide on a daily close, FILL AT THE NEXT DAY'S CLOSE — no same-bar fills):
  donchian N/M  enter when close > max(prior N closes); exit when close < min(prior M closes)
  ma L          hold while close > L-day simple moving average of closes
Fees per side: 0.05% equities (commission + half spread, liquid US large caps), 0.10%
commodities (futures/ETF proxy incl. roll slippage). Buy-and-hold pays one entry fee.

Pre-registered protocol (written before any out-of-sample number was looked at):
  in-sample      equities 2014-01-01 .. 2023-12-31; commodities 2017-01-01 .. 2023-12-31
                 (findata's futures history starts 2015-09) — every grid config runs here only.
  selection      per asset class, the config with the best equal-weight portfolio
                 CAGR / |maxDD| in-sample; only assets with the whole in-sample window (plus a
                 400-day indicator warm-up before it) count.
  out-of-sample  2024-01-01 .. latest close — ONLY the selected config is run.
  "trigger" verdict (all must hold, OOS, equal-weight 1/N no rebalancing):
     1. net return > 0
     2. CAGR/|maxDD| >= buy-and-hold's CAGR/|maxDD|
     3. at least half the assets have return/|maxDD| >= their own buy-and-hold's
  Otherwise the live scan presents these as observations (near 52-week high, deep drawdown,
  above/below the 200-day average) with no trigger language.

Result, 2026-09-27 run (latest bar 2026-09-25) — VERDICT: NOT A TRIGGER for either class.
  equity (46 OOS assets): in-sample pick donchian 100/50 (calmar 0.81 vs hold 0.56). OOS
    2024-01..2026-09: strategy +106.6% (CAGR +30.4%, maxDD -25.8%, calmar 1.18) vs hold
    +261.1% (CAGR +60.1%, maxDD -36.3%, calmar 1.65); only 10/46 assets beat their own hold on
    return/|maxDD|. Lower drawdown, but it gives back far more return than it saves.
  commodity (12): in-sample pick donchian 252/10 (calmar 0.24 vs hold 0.12). OOS: strategy
    +0.9% (maxDD -15.2%, calmar 0.02) vs hold +51.8% (maxDD -29.3%, calmar 0.56); 0/12 assets
    beat hold. (In-sample hold drawdowns are distorted by continuous-futures artifacts — CL's
    negative April 2020 print, a coffee glitch — the OOS window has neither.)
  → the live scan shows observations only (market_scan.py, migration 036).

Usage (CACHE = any scratch dir):
  sops exec-env secrets.env '.venv-bots/bin/python scripts/screen_daily_breakout.py fetch CACHE'
  .venv-bots/bin/python scripts/screen_daily_breakout.py run CACHE
"""

from __future__ import annotations

import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "strategies"))
sys.path.insert(0, str(_ROOT / "nautilus_equity"))

INDEXES = ["SPY", "QQQ", "IWM", "SMH"]
MEGA = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO"]
COMMODITIES = ["GC", "SI", "CL", "BZ", "HG", "NG", "PL", "PA", "KT", "ZW", "ZS", "ZC"]
FEE = {"equity": 0.0005, "commodity": 0.001}
IS_START = {"equity": pd.Timestamp("2014-01-01"), "commodity": pd.Timestamp("2017-01-01")}
IS_END = pd.Timestamp("2024-01-01")
WARMUP = pd.Timedelta(days=400)
GRID = ([("donchian", n, m) for n in (20, 55, 100, 150, 252) for m in (10, 20, 50, 100) if m < n]
        + [("ma", n, 0) for n in (50, 100, 200)])


def equity_universe() -> list[str]:
    import semi_analysis  # the /semis list; import is side-effect free
    out = list(INDEXES) + list(MEGA)
    out += [row[0] for row in semi_analysis.UNIVERSE if row[0] not in out]
    return out


def fetch(cache: Path) -> None:
    os.environ.setdefault("FINDATA_CACHE_DIR", str(cache / "findata"))
    import findata
    data: dict[str, tuple[str, list]] = {}
    for sym in equity_universe():
        bars = findata.closes_yahoo(sym)
        print(f"{sym:6} equity    {len(bars)} bars", flush=True)
        if bars:
            data[sym] = ("equity", bars)
    for sym in COMMODITIES:
        bars = findata.closes_commodity(sym, min_bars=3600, max_pages=13)
        print(f"{sym:6} commodity {len(bars)} bars (findata budget used today {findata.budget_used()})",
              flush=True)
        if bars:
            data[sym] = ("commodity", bars)
    pickle.dump(data, open(cache / "daily.pkl", "wb"))


def series(bars: list) -> pd.Series:
    s = pd.Series([c for _t, c in bars],
                  index=pd.to_datetime([t for t, _c in bars], unit="ms").normalize())
    return s[~s.index.duplicated(keep="last")].sort_index()


def target(close: pd.Series, kind: str, n: int, m: int) -> pd.Series:
    """1 = the rule wants to be long after this close, 0 = flat. Uses prior bars only."""
    if kind == "ma":
        return (close > close.rolling(n).mean()).astype(float).where(close.rolling(n).count() == n)
    hi = close.shift(1).rolling(n).max()
    lo = close.shift(1).rolling(m).min()
    state, out = 0.0, []
    for c, h, lw in zip(close.values, hi.values, lo.values):
        if np.isnan(h):
            out.append(np.nan)
            continue
        if state == 0 and c > h:
            state = 1.0
        elif state == 1 and c < lw:
            state = 0.0
        out.append(state)
    return pd.Series(out, index=close.index)


def equity_curve(close: pd.Series, want: pd.Series, start, end, fee: float) -> pd.Series | None:
    """Daily equity over [start, end): starts flat at the first bar; a decision on close t is
    filled at close t+1 (the position held over bar t+1's return is want[t-1])."""
    w = want[(want.index >= start) & (want.index < end)]
    c = close[(close.index >= start) & (close.index < end)]
    if len(c) < 60 or w.isna().any():
        return None
    ret = c.pct_change().fillna(0.0).values
    held = np.concatenate([[0.0], w.values[:-1]])        # decision t → exposure on bar t+1
    pos = np.concatenate([[0.0], held[:-1]])              # filled at close t+1 → earns from t+2
    trades = np.abs(np.diff(np.concatenate([[0.0], held])))
    eq = np.cumprod((1 + pos * ret) * (1 - fee * trades))
    return pd.Series(eq, index=c.index)


def hold_curve(close: pd.Series, start, end, fee: float) -> pd.Series | None:
    c = close[(close.index >= start) & (close.index < end)]
    if len(c) < 60:
        return None
    return c / c.iloc[0] * (1 - fee)


def stats(eq: pd.Series) -> dict:
    """eq starts at 1 (hold at 1 - fee), so eq[-1] - 1 is the net return."""
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    ret = eq.iloc[-1] - 1
    mdd = float((eq / eq.cummax() - 1).min())
    cagr = (1 + ret) ** (1 / years) - 1 if years > 0 and ret > -1 else -1.0
    return {"ret": float(ret), "mdd": mdd, "cagr": cagr, "years": years,
            "calmar": cagr / abs(mdd) if mdd < 0 else float("inf")}


def portfolio(curves: list[pd.Series]) -> pd.Series:
    """Equal-weight 1/N, no rebalancing: the mean of the normalised curves (ffilled)."""
    df = pd.concat(curves, axis=1, sort=True).ffill().dropna()
    return df.mean(axis=1)


def run_period(data, cls, cfg, start, end):
    """Only assets whose history covers the warm-up + the whole period take part."""
    per, s_curves, h_curves = {}, [], []
    for sym, (klass, bars) in data.items():
        if klass != cls:
            continue
        close = series(bars)
        if close.index[0] > start - WARMUP:
            continue
        eq = equity_curve(close, target(close, *cfg), start, end, FEE[cls])
        hd = hold_curve(close, start, end, FEE[cls])
        if eq is None or hd is None:
            continue
        s, h = stats(eq), stats(hd)
        n_trades = int(np.abs(np.diff(target(close, *cfg)[(close.index >= start) & (close.index < end)]
                                      .fillna(0).values)).sum())
        per[sym] = {"s": s, "h": h, "n": n_trades}
        s_curves.append(eq)
        h_curves.append(hd)
    if not per:
        return None
    return {"per": per, "s": stats(portfolio(s_curves)), "h": stats(portfolio(h_curves))}


def ratio(x: dict) -> float:
    return x["ret"] / abs(x["mdd"]) if x["mdd"] < 0 else float("inf")


def label(cfg) -> str:
    return f"donchian {cfg[1]}/{cfg[2]}" if cfg[0] == "donchian" else f"close > MA{cfg[1]}"


def main() -> int:
    cmd, cache = sys.argv[1], Path(sys.argv[2])
    cache.mkdir(parents=True, exist_ok=True)
    if cmd == "fetch":
        fetch(cache)
        return 0
    data = pickle.load(open(cache / "daily.pkl", "rb"))
    latest = max(series(b).index[-1] for _c, b in data.values())
    for cls in ("equity", "commodity"):
        print(f"\n===== {cls} — IN-SAMPLE ({IS_START[cls].date()} .. {IS_END.date()}), fees {FEE[cls] * 100:.2f}%/side =====")
        print(f"{'config':18} {'assets':>6} {'CAGR':>7} {'maxDD':>7} {'calmar':>6}   hold: "
              f"{'CAGR':>7} {'maxDD':>7} {'calmar':>6}")
        rows = []
        for cfg in GRID:
            r = run_period(data, cls, cfg, IS_START[cls], IS_END)
            if not r:
                continue
            rows.append((cfg, r))
            s, h = r["s"], r["h"]
            print(f"{label(cfg):18} {len(r['per']):6d} {s['cagr'] * 100:+6.1f}% {s['mdd'] * 100:6.1f}% "
                  f"{s['calmar']:6.2f}         {h['cagr'] * 100:+6.1f}% {h['mdd'] * 100:6.1f}% {h['calmar']:6.2f}")
        cfg, is_r = max(rows, key=lambda x: x[1]["s"]["calmar"])
        print(f"SELECTED in-sample: {label(cfg)} (calmar {is_r['s']['calmar']:.2f} vs hold "
              f"{is_r['h']['calmar']:.2f})")

        oos = run_period(data, cls, cfg, IS_END, latest + pd.Timedelta(days=1))
        print(f"\n----- {cls} OUT-OF-SAMPLE {IS_END.date()} .. {latest.date()} — {label(cfg)} only -----")
        print(f"{'asset':7} {'trades':>6} {'strat':>8} {'maxDD':>7} {'hold':>8} {'holdDD':>7} {'r/DD>=hold':>10}")
        wins = 0
        for sym, x in sorted(oos["per"].items(), key=lambda kv: -kv[1]["s"]["ret"]):
            ok = ratio(x["s"]) >= ratio(x["h"])
            wins += ok
            print(f"{sym:7} {x['n']:6d} {x['s']['ret'] * 100:+7.1f}% {x['s']['mdd'] * 100:6.1f}% "
                  f"{x['h']['ret'] * 100:+7.1f}% {x['h']['mdd'] * 100:6.1f}% {'yes' if ok else 'no':>10}")
        s, h, n = oos["s"], oos["h"], len(oos["per"])
        print(f"PORTFOLIO eq-wt ({n}): strat {s['ret'] * 100:+.1f}% (CAGR {s['cagr'] * 100:+.1f}%, "
              f"maxDD {s['mdd'] * 100:.1f}%, calmar {s['calmar']:.2f}) | hold {h['ret'] * 100:+.1f}% "
              f"(CAGR {h['cagr'] * 100:+.1f}%, maxDD {h['mdd'] * 100:.1f}%, calmar {h['calmar']:.2f})")
        c1, c2, c3 = s["ret"] > 0, s["calmar"] >= h["calmar"], wins * 2 >= n
        print(f"criteria: net>0 {c1} | calmar>=hold {c2} | assets r/DD>=hold {wins}/{n} {c3}")
        print(f"VERDICT {cls}: {'TRIGGER HOLDS UP' if c1 and c2 and c3 else 'NOT A TRIGGER — observations only'}")
    print(f"\nrun {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, latest bar {latest.date()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
