"""Fetch and explain futures context for price-triggered alerts.

The signal node already detects unusual price movement. This module adds the
missing question: is the move backed by new leverage, short covering, or
liquidation? It only uses Binance public endpoints and is called on alerts,
not every bar.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import requests

BASE_URL = "https://fapi.binance.com"
log = logging.getLogger("signal_context")


@dataclass(frozen=True)
class SignalContext:
    structure: str
    confidence: str
    funding: float | None
    open_interest_change: float | None
    taker_ratio: float | None
    long_short_ratio: float | None
    evidence: tuple[str, ...]
    watch: str


class MarketContextFetcher:
    """Load a small, explainable market context snapshot when an alert fires."""

    def __init__(self, session: Any = requests):
        self._session = session
        self._previous_oi: dict[str, float] = {}

    def fetch(self, symbol: str, price_change: float) -> SignalContext:
        symbol = symbol.replace("/", "").replace(".BINANCE", "")
        data = {
            "funding": self._get(
                "/fapi/v1/fundingRate", {"symbol": symbol, "limit": 1}
            ),
            "open_interest": self._get(
                "/fapi/v1/openInterest", {"symbol": symbol}
            ),
            "long_short": self._get(
                "/futures/data/globalLongShortAccountRatio",
                {"symbol": symbol, "period": "5m", "limit": 1},
            ),
            "taker": self._get(
                "/futures/data/takerlongshortRatio",
                {"symbol": symbol, "period": "5m", "limit": 1},
            ),
        }

        funding = _float(data["funding"], 0, "fundingRate")
        oi = _float(data["open_interest"], None, "openInterest")
        previous_oi = self._previous_oi.get(symbol)
        oi_change = (oi - previous_oi) / previous_oi if oi and previous_oi else None
        if oi is not None:
            self._previous_oi[symbol] = oi
        long_short = _float(data["long_short"], 0, "longShortRatio")
        taker = _float(data["taker"], 0, "buySellRatio")

        structure = _classify(price_change, oi_change)
        evidence = [
            f"funding {funding:+.4%}",
            f"OI {_format_change(oi_change)}",
            f"taker {taker:.2f}",
            f"L/S {long_short:.2f}",
        ]
        confidence = _confidence(price_change, oi_change, taker)
        watch = _watch_for(structure, price_change)
        return SignalContext(
            structure=structure,
            confidence=confidence,
            funding=funding,
            open_interest_change=oi_change,
            taker_ratio=taker,
            long_short_ratio=long_short,
            evidence=tuple(evidence),
            watch=watch,
        )

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            response = self._session.get(
                f"{BASE_URL}{path}", params=params, timeout=8
            )
            response.raise_for_status()
            payload = response.json()
            return payload[-1] if isinstance(payload, list) and payload else payload
        except (requests.RequestException, ValueError, TypeError) as exc:
            log.warning("context request failed for %s: %s", path, exc)
            return None


def _float(value: Any, default: float | None, key: str) -> float | None:
    if not isinstance(value, dict) or key not in value:
        return default
    try:
        return float(value[key])
    except (TypeError, ValueError):
        return default


def _classify(price_change: float, oi_change: float | None) -> str:
    if oi_change is None:
        return "price-only move"
    if price_change > 0 and oi_change > 0.001:
        return "new longs entering"
    if price_change > 0:
        return "short covering"
    if oi_change > 0.001:
        return "new shorts entering"
    return "long liquidation"


def _confidence(price_change: float, oi_change: float | None, taker: float) -> str:
    if oi_change is None:
        return "low"
    taker_confirms = (price_change > 0 and taker > 1.02) or (
        price_change < 0 and taker < 0.98
    )
    return "high" if taker_confirms and abs(oi_change) > 0.001 else "medium"


def _format_change(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:+.2%}"


def _watch_for(structure: str, price_change: float) -> str:
    if structure == "new longs entering":
        return "watch whether price holds the breakout while OI stays firm"
    if structure == "short covering":
        return "watch for a pullback; continuation needs fresh OI"
    if structure == "new shorts entering":
        return "watch whether price rejects the breakdown with OI still rising"
    if structure == "long liquidation":
        return "watch for stabilization; further downside needs renewed selling"
    return "wait for OI and taker flow to confirm the move"
