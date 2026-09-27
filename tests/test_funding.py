"""Tests for the perp-funding universe in strategies/signal_evaluator.py (opportunity scan).

Run: .venv-bots/bin/python -c "import sys; sys.path.insert(0,'tests'); import test_funding as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

import signal_evaluator as se  # noqa: E402


def test_perp_asset_strips_the_per_1000_prefix():
    assert se.perp_asset("1000PEPEUSDT") == "PEPE"
    assert se.perp_asset("BTCUSDT") == "BTC"


def test_universe_is_top_by_volume_plus_house_assets():
    tickers = [{"symbol": f"C{i}USDT", "quoteVolume": str(1000 - i)} for i in range(40)]
    tickers += [{"symbol": "1000PEPEUSDT", "quoteVolume": "1"},
                {"symbol": "BTCUSDT", "quoteVolume": "5000"},
                {"symbol": "ETHBTC", "quoteVolume": "9999"}]
    spot = {f"C{i}USDT" for i in range(40)} | {"PEPEUSDT", "BTCUSDT"}
    u = se.funding_universe(tickers, spot)
    assert "C0" in u and "C28" in u and "C29" not in u        # BTC takes one of the 30 slots
    assert u["PEPE"]["symbol"] == "1000PEPEUSDT"              # house asset found via its 1000x perp
    assert "ETHBTC"[:-3] not in u and "ETH" not in u          # non-USDT pairs ignored; no ETH perp here


def test_universe_drops_perp_only_listings():
    tickers = [{"symbol": "BTWUSDT", "quoteVolume": "9e9"}, {"symbol": "BTCUSDT", "quoteVolume": "1"}]
    assert list(se.funding_universe(tickers, {"BTCUSDT"})) == ["BTC"]
