"""Tests for strategies/share_card.py — cards render to 1200x675 PNGs for wins, losses,
backfilled trades and the scorecard (needs Pillow + a CJK font: SHARE_CARD_FONT or fc-match).

Run: .venv-bots/bin/python -c "import sys; sys.path.insert(0,'tests'); import test_share_card as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]; print('ok')"
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "strategies"))

from PIL import Image  # noqa: E402

import share_card as sc  # noqa: E402

UTC = timezone.utc
START = datetime(2026, 1, 1, 0, 59, tzinfo=UTC)


def rec(asset, sleeve, hold, open_ret=None):
    return {"asset": asset, "sleeve_ret": sleeve, "hold_ret": hold, "n_closed": 10,
            "n_wins": 4, "best_ret": 0.2 if asset == "SOL" else 0.1, "start_ts": START,
            "open_entry_ts": START if open_ret is not None else None, "open_ret": open_ret}


RECORD = [rec("BTC", 0.066, -0.04), rec("ETH", -0.07, -0.1, 0.018), rec("SOL", 0.15, -0.03, 0.14)]


def trade(net_ret, live=True):
    return {"asset": "ETH", "net_ret": net_ret, "live": live,
            "entry_ts": datetime(2026, 8, 19, 13, tzinfo=UTC), "entry_price": 1937.21,
            "exit_ts": datetime(2026, 9, 2, 10, tzinfo=UTC), "exit_price": 2376.61,
            "hold_days": 13.9}


def size(png: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(png)).size


def test_exit_card_win():
    assert size(sc.render_exit_card(trade(0.224), RECORD)) == (sc.W, sc.H)


def test_exit_card_loss_and_backfilled():
    assert size(sc.render_exit_card(trade(-0.069, live=False), RECORD)) == (sc.W, sc.H)


def test_scorecard():
    assert size(sc.render_scorecard(RECORD, datetime(2026, 9, 28, tzinfo=UTC))) == (sc.W, sc.H)


def test_portfolio_matches_equal_weight():
    p = sc._portfolio(RECORD)
    assert abs(p["ret"] - (0.066 - 0.07 + 0.15) / 3) < 1e-12
    assert p["closed"] == 30 and abs(p["win_rate"] - 0.4) < 1e-12 and p["best"] == ("SOL", 0.2)
