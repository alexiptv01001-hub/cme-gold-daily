"""Unit tests for the buy/sell heuristic."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from buy_sell import classify


def test_at_ask_is_buy():
    assert classify(price=10.0, bid=9.0, ask=10.0) == "Buy"


def test_at_bid_is_sell():
    assert classify(price=9.0, bid=9.0, ask=10.0) == "Sell"


def test_at_mid_is_mid():
    assert classify(price=9.5, bid=9.0, ask=10.0) == "Mid"


def test_just_below_ask_within_tolerance_is_buy():
    # 9.85 of [9.0, 10.0] = pos 0.85, default tolerance 0.20 → Buy
    assert classify(price=9.85, bid=9.0, ask=10.0) == "Buy"


def test_missing_bid_returns_mid():
    assert classify(price=10.0, bid=None, ask=10.5) == "Mid"


def test_zero_spread_returns_mid():
    assert classify(price=10.0, bid=10.0, ask=10.0) == "Mid"


def test_inverted_book_returns_mid():
    assert classify(price=10.0, bid=11.0, ask=10.0) == "Mid"


def test_tight_tolerance_pushes_more_to_mid():
    # pos 0.85 → with tolerance 0.05, threshold is 0.95 → "Mid"
    assert classify(price=9.85, bid=9.0, ask=10.0, tolerance=0.05) == "Mid"
