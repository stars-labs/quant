"""Opportunity radar for US equities + commodities (migration 036) — pure daily-close metrics.

Pure: no DB, no network, stdlib only. signal_evaluator.sweep_markets feeds it daily closes —
commodities from quant.market_snapshots (market_collector's findata pull, no extra API call),
equities from findata.closes_yahoo (free, cached per UTC day) — and upserts the result into
quant.market_scan. The Telegram digest and /scan read that table.

OBSERVATIONS, NOT TRIGGERS. scripts/screen_daily_breakout.py tested the daily breakout /
moving-average rules on these exact assets (parameters picked on 2014-2023, verified on
2024-now, net of fees, vs buy-and-hold): the in-sample pick lost to buy-and-hold out of
sample in both classes — numbers in that script's docstring. Until a rule passes that screen, nothing here is presented as a buy or sell
call — only where each price sits against its own 52-week closing high and 200-day average.
"""

from __future__ import annotations

HIGH_LB = 252   # ~52 weeks of trading days — the closing-high reference
MA_LB = 200     # 200-day simple moving average of closes (long-term trend)
MONTH_LB = 21   # ~1 month of trading days

# Consumers' thresholds (Telegram digest + web $lib/scan.ts — keep in lockstep).
NEAR_HIGH = -0.02   # within 2% of the 52-week closing high
DEEP_DD = -0.30     # 30%+ below the 52-week closing high

# The fixed part of the equity universe; quant.semi_universe (the /semis NVDA supply chain)
# is added at sweep time. (symbol, group, zh, en). Tickers stay as-is in both languages.
EQUITY_CORE = [
    ("SPY", "index", "标普 500", "S&P 500"), ("QQQ", "index", "纳指 100", "Nasdaq 100"),
    ("IWM", "index", "罗素 2000", "Russell 2000"), ("SMH", "index", "半导体 ETF", "Semis ETF"),
    ("AAPL", "mega", "苹果", "Apple"), ("MSFT", "mega", "微软", "Microsoft"),
    ("NVDA", "mega", "英伟达", "NVIDIA"), ("AMZN", "mega", "亚马逊", "Amazon"),
    ("GOOGL", "mega", "谷歌", "Alphabet"), ("META", "mega", "Meta", "Meta"),
    ("TSLA", "mega", "特斯拉", "Tesla"), ("AVGO", "mega", "博通", "Broadcom"),
]

# findata continuous-future symbol → group (names come with market_collector's snapshot).
COMMODITY_GROUP = {"GC": "metals", "SI": "metals", "PL": "metals", "PA": "metals", "HG": "metals",
                   "CL": "energy", "BZ": "energy", "NG": "energy",
                   "KT": "ags", "ZW": "ags", "ZS": "ags", "ZC": "ags"}


def metrics(bars: list[tuple[int, float]]) -> dict | None:
    """Daily closes [(unix_ms, close), ...] oldest→newest → the scan row's numbers.

    None when there is not a full 52-week lookback (a partial window would call a fresh
    listing "at its 52-week high"). The last bar is included in its own windows: a close AT
    the high reads 0.0 from it.
    """
    if len(bars) < HIGH_LB or any(c <= 0 for _t, c in bars[-HIGH_LB:]):
        return None
    closes = [c for _t, c in bars]
    last = closes[-1]
    high = max(closes[-HIGH_LB:])
    low = min(closes[-HIGH_LB:])
    ma = sum(closes[-MA_LB:]) / MA_LB
    return {
        "last_ts": bars[-1][0],
        "last_close": last,
        "high_52w": high,
        "low_52w": low,
        "from_high_52w": last / high - 1,
        "ma200": ma,
        "vs_ma200": last / ma - 1,
        "ret_1m": last / closes[-1 - MONTH_LB] - 1,
    }


def is_near_high(row: dict) -> bool:
    return row.get("from_high_52w") is not None and row["from_high_52w"] >= NEAR_HIGH


def is_deep(row: dict) -> bool:
    return row.get("from_high_52w") is not None and row["from_high_52w"] <= DEEP_DD


def breadth(rows: list[dict]) -> tuple[int, int]:
    """(above the 200-day average, rows with a 200-day average)."""
    known = [r for r in rows if r.get("vs_ma200") is not None]
    return sum(r["vs_ma200"] > 0 for r in known), len(known)
