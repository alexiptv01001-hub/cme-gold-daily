"""Unit tests for the strategy classifier."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from strategy import classify
from trades import OptionLeg, TradeRecord


def _trade(*legs: OptionLeg, trade_type: str = "Spread") -> TradeRecord:
    return TradeRecord(
        venue="BLOCK", time_ct="10:00 AM", trade_type=trade_type,
        option_legs=list(legs))


def _opt(strike: float, is_call: bool, side: str, qty: int = 10,
         price: float = 5.0, expiry: str = "OGM6") -> OptionLeg:
    return OptionLeg(
        expiry_code=expiry, underlying_code="GCM6",
        is_call=is_call, strike=strike, side=side, qty=qty, price=price)


def test_classify_long_call():
    s = classify(_trade(_opt(4800, True, "Buy"), trade_type="Option"))
    assert s.kind == "call_long"
    assert s.direction == "bullish"


def test_classify_short_put():
    s = classify(_trade(_opt(4500, False, "Sell"), trade_type="Option"))
    assert s.kind == "put_short"
    assert s.direction == "bullish"


def test_classify_bull_call_spread():
    s = classify(_trade(
        _opt(4800, True, "Buy", price=20),
        _opt(4900, True, "Sell", price=12),
    ))
    assert s.kind == "call_vertical_bull"
    assert s.direction == "bullish"
    # primary_legs ordered low/high
    assert s.primary_legs[0].strike == 4800
    assert s.primary_legs[1].strike == 4900


def test_classify_bear_call_spread():
    s = classify(_trade(
        _opt(4800, True, "Sell", price=20),
        _opt(4900, True, "Buy", price=12),
    ))
    assert s.kind == "call_vertical_bear"
    assert s.direction == "bearish"


def test_classify_bear_put_spread():
    s = classify(_trade(
        _opt(4500, False, "Sell", price=8),
        _opt(4700, False, "Buy", price=20),
    ))
    assert s.kind == "put_vertical_bear"
    assert s.direction == "bearish"


def test_classify_bull_put_spread():
    s = classify(_trade(
        _opt(4500, False, "Buy", price=8),
        _opt(4700, False, "Sell", price=20),
    ))
    assert s.kind == "put_vertical_bull"
    assert s.direction == "bullish"


def test_classify_long_straddle():
    s = classify(_trade(
        _opt(4700, True, "Buy", price=30),
        _opt(4700, False, "Buy", price=28),
    ))
    assert s.kind == "straddle_long"
    assert s.direction == "neutral_breakout"


def test_classify_short_strangle():
    s = classify(_trade(
        _opt(4500, False, "Sell", price=8),
        _opt(4900, True, "Sell", price=10),
    ))
    assert s.kind == "strangle_short"
    assert s.direction == "neutral_range"


def test_classify_bull_risk_reversal():
    s = classify(_trade(
        _opt(4500, False, "Sell", price=8),
        _opt(4900, True, "Buy", price=10),
    ))
    assert s.kind == "risk_reversal_bull"
    assert s.direction == "bullish"


def test_classify_calendar_multi_expiry():
    s = classify(_trade(
        _opt(4750, True, "Buy", expiry="OGN6"),
        _opt(4800, True, "Sell", expiry="OGQ6"),
        _opt(4850, True, "Buy", expiry="OGU6"),
    ))
    assert s.kind == "calendar"
    assert s.direction == "unknown"


def test_classify_three_leg_complex_falls_back():
    s = classify(_trade(
        _opt(4500, False, "Buy"),
        _opt(4700, True, "Sell"),
        _opt(4900, True, "Buy"),
    ))
    assert s.kind == "complex"
    assert len(s.primary_legs) == 3
