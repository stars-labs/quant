"""Stage 8 / P2 — the single-stack signal layer as a data-only Nautilus live node.

Subscribes to Binance **mainnet** public minute bars (real prices) and runs the
``SignalAlerter`` actor to emit Telegram spike (PUMP/DUMP) + accumulation-dip (FLASH/FAST)
alerts. This is the Nautilus replacement for the retired standalone ``event_reactor.py`` /
``event_dca_bot.py`` daemons.

Why mainnet data while execution stays testnet: spike/dip signals must reflect live prices.
**This node never trades** — it has no execution client, holds no keys for trading, and risks
no money. It only reads public market data and sends Telegram messages.

Env:
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID   alert sink (sops); absent → detects but doesn't send
  SIGNAL_INSTRUMENTS   space/comma list (default BTCUSDT.BINANCE ETHUSDT.BINANCE SOLUSDT.BINANCE)
  SIGNAL_BAR           bar spec (default 1-MINUTE-LAST-EXTERNAL)
  BINANCE_API_KEY / BINANCE_API_SECRET[_FILE]   optional — only set if Binance rate-limits anon

Validate wiring offline (constructs + build(), does NOT connect):
  python run_signal_alerter.py --check
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.adapters.binance.common.enums import BinanceAccountType, BinanceEnvironment
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig
from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
from nautilus_trader.config import (
    InstrumentProviderConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signal_alerter import SignalAlerter  # noqa: E402
from signal_context import MarketContextFetcher  # noqa: E402
from telegram_notifier import TelegramNotifier  # noqa: E402

DEFAULT_INSTRUMENTS = "BTCUSDT.BINANCE ETHUSDT.BINANCE SOLUSDT.BINANCE"


def _instruments() -> list[str]:
    raw = os.environ.get("SIGNAL_INSTRUMENTS", DEFAULT_INSTRUMENTS)
    return [tok for tok in raw.replace(",", " ").split() if tok]


def build_node() -> TradingNode:
    # Mainnet public data only. Instruments + bars load anonymously via Binance's public
    # exchangeInfo / WebSocket — NO keys needed. Critically, we must pass *no* key when none
    # is set: a placeholder/garbage key forces an authenticated fee-tier call that hard-fails
    # (-2008 Invalid Api-Key) and aborts instrument loading. Keys are threaded through only
    # if genuinely provided (e.g. a real read-only mainnet key to lift anon rate limits).
    api_key = os.environ.get("BINANCE_API_KEY") or None
    api_secret = os.environ.get("BINANCE_API_SECRET")
    if not api_secret:
        secret_file = os.environ.get("BINANCE_API_SECRET_FILE")
        if secret_file and Path(secret_file).exists():
            api_secret = Path(secret_file).read_text().strip()
    api_secret = api_secret or None

    provider = InstrumentProviderConfig(load_all=True)
    data_client_kwargs = dict(
        account_type=BinanceAccountType.SPOT,
        environment=BinanceEnvironment.LIVE,  # mainnet prices; no exec client = no trading
        instrument_provider=provider,
    )
    # Only include creds when present so the adapter takes the anonymous public path otherwise.
    if api_key and api_secret:
        data_client_kwargs["api_key"] = api_key
        data_client_kwargs["api_secret"] = api_secret

    config = TradingNodeConfig(
        trader_id="SIGNAL-001",
        logging=LoggingConfig(log_level="INFO"),
        data_clients={"BINANCE": BinanceDataClientConfig(**data_client_kwargs)},
        # No exec_clients — this node cannot place orders.
    )

    node = TradingNode(config=config)
    node.add_data_client_factory("BINANCE", BinanceLiveDataClientFactory)
    node.build()

    bar_spec = os.environ.get("SIGNAL_BAR", "1-MINUTE-LAST-EXTERNAL")
    notifier = TelegramNotifier()
    alerter = SignalAlerter(
        _instruments(),
        bar_spec=bar_spec,
        notifier=notifier,
        context_fetcher=MarketContextFetcher(),
    )
    node.trader.add_actor(alerter)
    return node


def main() -> int:
    check_only = "--check" in sys.argv
    node = build_node()
    print(
        f"Signal node built OK (venue={BINANCE_VENUE}, MAINNET data-only, "
        f"instruments={_instruments()}, telegram={'on' if TelegramNotifier().enabled else 'off'})"
    )
    if check_only:
        node.dispose()
        return 0
    try:
        node.run()
    finally:
        node.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
