"""Tests for explainable futures context classification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signal_context import _classify, _confidence  # noqa: E402


def test_rising_price_and_oi_is_new_longs():
    assert _classify(0.02, 0.03) == "new longs entering"


def test_rising_price_without_oi_is_short_covering():
    assert _classify(0.02, -0.01) == "short covering"


def test_falling_price_and_oi_is_new_shorts():
    assert _classify(-0.02, 0.03) == "new shorts entering"


def test_taker_flow_confirms_with_high_confidence():
    assert _confidence(0.02, 0.03, 1.1) == "high"


def test_missing_oi_is_low_confidence():
    assert _confidence(-0.02, None, 0.9) == "low"
