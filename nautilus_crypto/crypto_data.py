"""Load freqtrade Binance feather OHLCV into NautilusTrader bars, and load the
Fear & Greed history. Real local data — no exchange account needed.

freqtrade stores spot OHLCV at user_data/data/binance/<BASE>_<QUOTE>-<TF>.feather with
columns: date (tz-aware), open, high, low, close, volume.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.persistence.wranglers import prepare_event_and_init_timestamps

_REPO = Path(__file__).resolve().parent.parent
_BINANCE = _REPO / "user_data" / "data" / "binance"
_FNG_CSV = _REPO / "data" / "fng_history.csv"


def load_bars(instrument, pair_file: str, bar_type: BarType):
    """pair_file e.g. 'BTC_USDT-1d'. Returns a list of Nautilus Bar objects."""
    df = pd.read_feather(_BINANCE / f"{pair_file}.feather")
    # Not BarDataWrangler.process(): it maps `_build_bar(double[:] values, ...)` over
    # `data.values`, and under pandas >= 3 (Copy-on-Write always on) `.values` of an
    # all-float frame is a READ-ONLY view -> Cython's non-const memoryview raises
    # "buffer source array is read-only". Hand it a writable copy of the same rows instead
    # (index forced to UTC nanoseconds: feather stores ms, and the helper views raw ints).
    values = df[["open", "high", "low", "close", "volume"]].to_numpy(dtype="float64", copy=True)
    ts_events, ts_inits = prepare_event_and_init_timestamps(
        pd.DatetimeIndex(df["date"]).tz_convert("UTC").as_unit("ns"), 0
    )
    wrangler = BarDataWrangler(bar_type, instrument)
    return list(map(wrangler._build_bar, values, ts_events, ts_inits))


class FngSeries:
    """Fear & Greed index by date. Missing dates fall back to `default` (neutral)."""

    def __init__(self, csv_path: Path | None = None, default: int = 50):
        self.default = default
        self._by_date: dict[str, int] = {}
        # Allow prod/deploy to point at a runtime-fetched FNG CSV via env, since the
        # repo-relative default path doesn't exist inside the Nix store / on the server.
        import os

        path = Path(csv_path or os.environ.get("FNG_CSV") or _FNG_CSV)
        if path.exists():
            with open(path) as f:
                for row in csv.DictReader(f):
                    try:
                        self._by_date[row["date"]] = int(row["value"])
                    except (KeyError, ValueError):
                        continue

    def value_on(self, when) -> int:
        key = when.strftime("%Y-%m-%d")
        return self._by_date.get(key, self.default)

    def __len__(self):
        return len(self._by_date)
