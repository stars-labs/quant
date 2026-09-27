"""Stage 4 (equity) — US-equity LIVE execution on NautilusTrader via Interactive Brokers.

Runs the SAME HonestTrendEquity strategy used in backtest under a live TradingNode
against an IB Gateway / TWS. This is the equity counterpart to
`nautilus_crypto/live_accumulation.py`. Defaults to the IB **paper** account so the
execution path — connect, subscribe, order, fill, reconcile — can be proven before
touching a real account.

HARD GUARDRAIL: PAPER ONLY. The Gateway must be logged into a paper account
(account id DUQ*). `IB_TRADING_MODE` defaults to "paper"; this node refuses to build
when it is anything else unless `IB_ALLOW_LIVE=1` is explicitly set (never do this here).

Live config (defaults = the deployed recommendation, see STRATEGY_LEADERBOARD.md
"US Equity (HonestTrend, real IB data)"): **1-HOUR bars, EMA 50/100** — the most robust
config across NVDA/AMD/QQQ (every asset profitable, highest worst-asset Sharpe, moderate
turnover, least curve-fit). Override any knob via env.

Connection via env (mirrors download_ib.py):
  IB_HOST       (default 127.0.0.1)
  IB_PORT       (default 4002 = Gateway paper; TWS paper = 7497)
  IB_CLIENT_ID  (default 8 — dedicated live-node client id; download uses 5, order test 7)
  IB_ACCOUNT    (default DUQ654554 — the paper account; the IB exec client REQUIRES it,
                the adapter does NOT auto-discover the logged-in account. Override for a
                different paper account; falls back to TWS_ACCOUNT if explicitly cleared.)
  IB_BAR        (default 1-HOUR-LAST-EXTERNAL = recommended live timeframe; daily =
                1-DAY-LAST-EXTERNAL)

Strategy config (defaults = recommended live config; override via env):
  EQ_EMA_FAST       (default 50)
  EQ_EMA_SLOW       (default 100)
  EQ_ADX_THRESHOLD  (default 18.0)
  EQ_RISK_FRAC      (default 0.10)
  EQ_STOP_LOSS_PCT  (default 0.08 = −8% exchange-side protective stop)
  EQ_RTH_ONLY       (default 1 = gate entries to US regular trading hours; 0 disables)
  EQ_WARMUP_DAYS    (default 60 = calendar days of history requested at start to warm the
                    indicators; without it EMA 100 on 1h RTH bars needs ~14 trading days of
                    uptime and the node never trades)

Restarts are safe: the strategy does not flatten on stop, and each instance claims its
instrument's reconciled position + GTC stop (external_order_claims) and resumes managing it.

The IB instrument provider does NOT support load_all — instruments are loaded by id
(NVDA.NASDAQ, AMD.NASDAQ, QQQ.NASDAQ), matching the ids produced by download_ib.py.

Validate wiring without connecting (constructs the node, does not run):
  nautilus_equity/.venv/bin/python nautilus_equity/live_honest_equity.py --check
Run against the logged-in paper Gateway:
  nautilus_equity/.venv/bin/python nautilus_equity/live_honest_equity.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ibapi.common import MarketDataTypeEnum as IBMarketDataTypeEnum
from nautilus_trader.adapters.interactive_brokers.common import IB_VENUE
from nautilus_trader.adapters.interactive_brokers.config import (
    InteractiveBrokersDataClientConfig,
    InteractiveBrokersExecClientConfig,
    InteractiveBrokersInstrumentProviderConfig,
)
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.config import LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

sys.path.insert(0, str(Path(__file__).resolve().parent))
from honest_trend_equity import HonestTrendEquity, HonestTrendEquityConfig  # noqa: E402

# Same universe as download_ib.py. IB_SIMPLIFIED symbology → "<SYMBOL>.<VENUE>".
INSTRUMENTS = ["NVDA.NASDAQ", "AMD.NASDAQ", "QQQ.NASDAQ"]

# Default IB paper account (the exec client REQUIRES an account id; the adapter does NOT
# auto-discover the logged-in account). HARD GUARDRAIL: this MUST be a paper account (DU*).
_DEFAULT_PAPER_ACCOUNT = "DUQ654554"

# IB market-data type. A PAPER account has no real-time US-equity data subscription, so
# the default REALTIME stream returns nothing (the node subscribes, IB answers with
# error 162 "…connected from a different IP address" / no ticks, and the strategy starves
# — zero bars, never trades). DELAYED_FROZEN uses IB's free 15-min delayed feed which needs
# no subscription — correct for the paper soak. Override EQ_MARKET_DATA_TYPE=REALTIME once a
# live market-data subscription is attached to the account. (per IB adapter config docs.)
_MD_TYPES = {
    "REALTIME": IBMarketDataTypeEnum.REALTIME,
    "FROZEN": IBMarketDataTypeEnum.FROZEN,
    "DELAYED": IBMarketDataTypeEnum.DELAYED,
    "DELAYED_FROZEN": IBMarketDataTypeEnum.DELAYED_FROZEN,
}

# Recommended live config (see STRATEGY_LEADERBOARD.md US Equity section): 1h EMA 50/100.
_DEFAULT_BAR = "1-HOUR-LAST-EXTERNAL"
_DEFAULT_EMA_FAST = "50"
_DEFAULT_EMA_SLOW = "100"


def build_node() -> TradingNode:
    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4002"))  # Gateway paper; TWS paper = 7497
    client_id = int(os.environ.get("IB_CLIENT_ID", "8"))  # dedicated live node; 5=download, 7=order test
    # The IB exec client REQUIRES an account id (it does not auto-discover the logged-in
    # account): default to the paper account, allow IB_ACCOUNT / TWS_ACCOUNT override.
    account_id = (
        os.environ.get("IB_ACCOUNT")
        or os.environ.get("TWS_ACCOUNT")
        or _DEFAULT_PAPER_ACCOUNT
    )
    trading_mode = os.environ.get("IB_TRADING_MODE", "paper")

    # HARD GUARDRAIL: PAPER ONLY. Refuse non-paper mode, and refuse a non-paper account id
    # (paper accounts start with "DU") unless live is explicitly (never) unlocked.
    live_unlocked = os.environ.get("IB_ALLOW_LIVE") == "1"
    if trading_mode != "paper" and not live_unlocked:
        raise SystemExit(
            f"Refusing to build: IB_TRADING_MODE={trading_mode!r} but this node is PAPER-ONLY. "
            "Set IB_TRADING_MODE=paper (live trading is deliberately not enabled here)."
        )
    if not account_id.startswith("DU") and not live_unlocked:
        raise SystemExit(
            f"Refusing to build: IB_ACCOUNT={account_id!r} is not a paper account (DU*). "
            "This node is PAPER-ONLY."
        )

    instrument_ids = frozenset(InstrumentId.from_str(s) for s in INSTRUMENTS)
    provider = InteractiveBrokersInstrumentProviderConfig(load_ids=instrument_ids)

    md_type_name = os.environ.get("EQ_MARKET_DATA_TYPE", "DELAYED_FROZEN").upper()
    if md_type_name not in _MD_TYPES:
        raise SystemExit(
            f"EQ_MARKET_DATA_TYPE={md_type_name!r} invalid; choose one of {sorted(_MD_TYPES)}"
        )
    market_data_type = _MD_TYPES[md_type_name]

    config = TradingNodeConfig(
        trader_id="HONEST-EQUITY-001",
        logging=LoggingConfig(log_level="INFO"),
        data_clients={
            IB_VENUE.value: InteractiveBrokersDataClientConfig(
                ibg_host=host,
                ibg_port=port,
                ibg_client_id=client_id,
                instrument_provider=provider,
                use_regular_trading_hours=True,
                market_data_type=market_data_type,
            )
        },
        exec_clients={
            IB_VENUE.value: InteractiveBrokersExecClientConfig(
                ibg_host=host,
                ibg_port=port,
                ibg_client_id=client_id,
                account_id=account_id,
                instrument_provider=provider,
            )
        },
    )

    node = TradingNode(config=config)
    node.add_data_client_factory(IB_VENUE.value, InteractiveBrokersLiveDataClientFactory)
    node.add_exec_client_factory(IB_VENUE.value, InteractiveBrokersLiveExecClientFactory)
    node.build()

    # Recommended live timeframe = 1-HOUR-LAST-EXTERNAL (EMA 50/100). IB_BAR overrides
    # (e.g. 1-DAY-LAST-EXTERNAL for a low-touch daily cadence).
    bar_spec = os.environ.get("IB_BAR", _DEFAULT_BAR)
    for iid in INSTRUMENTS:
        strategy = HonestTrendEquity(
            HonestTrendEquityConfig(
                instrument_id=iid,
                bar_type=BarType.from_str(f"{iid}-{bar_spec}"),
                external_order_claims=[InstrumentId.from_str(iid)],
                flatten_on_stop=False,
                warmup_days=int(os.environ.get("EQ_WARMUP_DAYS", "60")),
                ema_fast=int(os.environ.get("EQ_EMA_FAST", _DEFAULT_EMA_FAST)),
                ema_slow=int(os.environ.get("EQ_EMA_SLOW", _DEFAULT_EMA_SLOW)),
                adx_threshold=float(os.environ.get("EQ_ADX_THRESHOLD", "18.0")),
                risk_frac=float(os.environ.get("EQ_RISK_FRAC", "0.10")),
                stop_loss_pct=float(os.environ.get("EQ_STOP_LOSS_PCT", "0.08")),
                rth_only=os.environ.get("EQ_RTH_ONLY", "1") != "0",
                # IB paper account base currency may not be USD (e.g. SGD). The stocks are
                # USD-quoted, so convert the base-currency equity to USD for sizing. Set
                # EQ_QUOTE_PER_BASE_FX to USD-per-1-base-unit (SGD base → ~0.74). Default
                # 1.0 = USD base (no conversion); leaving it unset on an SGD account would
                # over-size by the USD/SGD factor (~1.35x).
                quote_per_base_fx=float(os.environ.get("EQ_QUOTE_PER_BASE_FX", "1.0")),
            )
        )
        node.trader.add_strategy(strategy)

    return node


def main() -> int:
    check_only = "--check" in sys.argv
    node = build_node()  # constructing + build() validates the full live wiring offline
    print(
        f"TradingNode built OK (venue={IB_VENUE.value}, "
        f"host={os.environ.get('IB_HOST', '127.0.0.1')}, "
        f"port={os.environ.get('IB_PORT', '4002')}, "
        f"client_id={os.environ.get('IB_CLIENT_ID', '8')}, "
        f"account={os.environ.get('IB_ACCOUNT') or os.environ.get('TWS_ACCOUNT') or _DEFAULT_PAPER_ACCOUNT}, "
        f"mode={os.environ.get('IB_TRADING_MODE', 'paper')}, "
        f"bar={os.environ.get('IB_BAR', _DEFAULT_BAR)}, "
        f"ema={os.environ.get('EQ_EMA_FAST', _DEFAULT_EMA_FAST)}/"
        f"{os.environ.get('EQ_EMA_SLOW', _DEFAULT_EMA_SLOW)}, "
        f"instruments={INSTRUMENTS})"
    )

    if check_only:
        print("--check: wiring validated, not connecting.")
        node.dispose()
        return 0

    try:
        node.run()
    finally:
        node.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
