"""Live crypto trend node on NautilusTrader (Binance spot testnet): executes the PUBLIC house
signals (quant.strategy_signals, Donchian 1h 168/72 computed by strategies/signal_evaluator.py
on mainnet bars) — one SignalFollower per asset. See signal_follower.py for why it follows the
record instead of recomputing the rule on testnet bars, and how restarts resume.

Env: BINANCE_API_KEY, BINANCE_API_SECRET or BINANCE_API_SECRET_FILE (Ed25519 PEM),
     BINANCE_TESTNET=1 (default), TIMESCALE_URL (signals + ledger; required to trade),
     TREND_ASSETS (default: the 13 house assets, == strategies/strategy_record.ASSETS),
     TREND_NOTIONAL_USDT (default 500 per entry), TREND_POLL_SECS (default 60).

Validate wiring offline:  python live_trend.py --check
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.adapters.binance.common.enums import BinanceAccountType, BinanceEnvironment
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceExecClientConfig
from nautilus_trader.adapters.binance.factories import (
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.config import InstrumentProviderConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from signal_follower import SignalBook, SignalFollower, SignalFollowerConfig  # noqa: E402
from trade_ledger import TradeLedger  # noqa: E402

TRADER_ID = "TREND-001"
# Must equal strategies/strategy_record.ASSETS (test_signal_follower checks it). All 13 are
# listed on the Binance spot testnet (exchangeInfo status TRADING, checked 2026-09-27).
HOUSE_ASSETS = ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "SUI", "NEAR", "UNI", "ZEC",
                "PEPE", "WLD")


def _secret() -> str:
    s = os.environ.get("BINANCE_API_SECRET")
    if not s:
        f = os.environ.get("BINANCE_API_SECRET_FILE")
        if f and Path(f).exists():
            s = Path(f).read_text().strip()
    return s or "CHECK_ONLY_NO_CONNECT"


def build_node() -> TradingNode:
    if os.environ.get("BINANCE_TESTNET", "1") == "0":
        raise SystemExit("live_trend is TESTNET-only (guardrail): unset BINANCE_TESTNET=0")
    env = BinanceEnvironment.TESTNET
    api_key = os.environ.get("BINANCE_API_KEY") or "CHECK_ONLY_NO_CONNECT"
    api_secret = _secret()
    provider = InstrumentProviderConfig(load_all=True)

    config = TradingNodeConfig(
        trader_id=TRADER_ID,
        logging=LoggingConfig(log_level="INFO"),
        data_clients={
            "BINANCE": BinanceDataClientConfig(
                api_key=api_key, api_secret=api_secret,
                account_type=BinanceAccountType.SPOT, environment=env,
                instrument_provider=provider,
            )
        },
        exec_clients={
            "BINANCE": BinanceExecClientConfig(
                api_key=api_key, api_secret=api_secret,
                account_type=BinanceAccountType.SPOT, environment=env,
                instrument_provider=provider,
            )
        },
    )
    node = TradingNode(config=config)
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)
    node.add_exec_client_factory("BINANCE", BinanceLiveExecClientFactory)
    node.build()

    assets = [a.strip() for a in os.environ.get("TREND_ASSETS", ",".join(HOUSE_ASSETS)).split(",")
              if a.strip()]
    notional = float(os.environ.get("TREND_NOTIONAL_USDT", "500"))
    poll = int(os.environ.get("TREND_POLL_SECS", "60"))
    url = os.environ.get("TIMESCALE_URL", "")
    book = SignalBook(url)
    ledger = TradeLedger()

    for asset in assets:
        iid = f"{asset}USDT.BINANCE"
        # Resume what this node already holds (fails loudly if the DB is unreachable —
        # trading without knowing the holding could double-buy).
        held = ledger.open_row(TRADER_ID, iid) if url else None
        qty, px = held if held else (0.0, 0.0)
        node.trader.add_strategy(SignalFollower(
            SignalFollowerConfig(
                instrument_id=iid, notional_usdt=notional, poll_secs=poll,
                held_qty=qty, held_px=px,
                order_id_tag=asset[:8],  # distinct per instance
            ),
            book=book, ledger=ledger,
        ))
    return node


def main() -> int:
    check_only = "--check" in sys.argv
    has_keys = bool(os.environ.get("BINANCE_API_KEY")) and (
        bool(os.environ.get("BINANCE_API_SECRET"))
        or (os.environ.get("BINANCE_API_SECRET_FILE") and Path(os.environ["BINANCE_API_SECRET_FILE"]).exists())
    )
    if has_keys and not check_only and not os.environ.get("TIMESCALE_URL"):
        print("TIMESCALE_URL is required to trade: the node follows quant.strategy_signals "
              "and resumes holdings from quant.nautilus_trades.")
        return 2
    node = build_node()
    print(f"Trend (signal follower) TradingNode built OK (venue={BINANCE_VENUE}, testnet=True)")
    if check_only or not has_keys:
        if not has_keys:
            print("No BINANCE creds in env → not connecting.")
        node.dispose()
        return 0
    try:
        node.run()
    finally:
        node.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
