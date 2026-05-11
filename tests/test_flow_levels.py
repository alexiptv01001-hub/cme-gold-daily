"""Unit tests for the flow-levels math."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flow_levels import (
    BEARISH_TARGET, BULLISH_TARGET, EXPECTED_MOVE_HIGH,
    EXPECTED_MOVE_LOW, RANGE_HIGH, RANGE_LOW, RESISTANCE, SUPPORT,
    levels_for,
)
from strategy import classify
from trades import OptionLeg, TradeRecord


def _trade(*legs: OptionLeg) -> TradeRecord:
    return TradeRecord(venue="BLOCK", time_ct="10:00 AM",
                       trade_type="Spread", option_legs=list(legs))


def _opt(strike: float, is_call: bool, side: str, qty: int = 10,
         price: float = 5.0, expiry: str = "OGM6") -> OptionLeg:
    return OptionLeg(expiry_code=expiry, underlying_code="GCM6",
                     is_call=is_call, strike=strike, side=side,
                     qty=qty, price=price)


def test_long_call_bullish_target_strike_plus_premium():
    t = _trade(_opt(4800, True, "Buy", price=15))
    levels = levels_for(t, classify(t))
    assert len(levels) == 1
    assert levels[0].kind == BULLISH_TARGET
    assert levels[0].price == 4815  # 4800 + 15


def test_short_call_resistance_strike_plus_premium():
    t = _trade(_opt(4800, True, "Sell", price=15))
    levels = levels_for(t, classify(t))
    assert levels[0].kind == RESISTANCE
    assert levels[0].price == 4815


def test_long_put_bearish_target_strike_minus_premium():
    t = _trade(_opt(4500, False, "Buy", price=12))
    levels = levels_for(t, classify(t))
    assert levels[0].kind == BEARISH_TARGET
    assert levels[0].price == 4488  # 4500 - 12


def test_short_put_support_strike_minus_premium():
    t = _trade(_opt(4500, False, "Sell", price=12))
    levels = levels_for(t, classify(t))
    assert levels[0].kind == SUPPORT
    assert levels[0].price == 4488


def test_bull_call_spread_lower_plus_net_debit():
    # Long 4800 @20  Short 4900 @12  → net debit 8 → target 4808
    t = _trade(
        _opt(4800, True, "Buy", price=20),
        _opt(4900, True, "Sell", price=12),
    )
    levels = levels_for(t, classify(t))
    assert len(levels) == 1
    assert levels[0].kind == BULLISH_TARGET
    assert levels[0].price == 4808.0


def test_bear_put_spread_upper_minus_net_debit():
    # Long 4700 @20  Short 4500 @8 → net debit 12 → target 4700-12 = 4688
    t = _trade(
        _opt(4500, False, "Sell", price=8),
        _opt(4700, False, "Buy", price=20),
    )
    levels = levels_for(t, classify(t))
    assert len(levels) == 1
    assert levels[0].kind == BEARISH_TARGET
    assert levels[0].price == 4688.0


def test_long_straddle_emits_em_high_and_low():
    # 4700 straddle for $30 + $28 = $58 total → EM endpoints 4642 / 4758
    t = _trade(
        _opt(4700, True, "Buy", price=30),
        _opt(4700, False, "Buy", price=28),
    )
    levels = levels_for(t, classify(t))
    kinds = {l.kind for l in levels}
    assert {EXPECTED_MOVE_HIGH, EXPECTED_MOVE_LOW} <= kinds
    high = next(l for l in levels if l.kind == EXPECTED_MOVE_HIGH)
    low = next(l for l in levels if l.kind == EXPECTED_MOVE_LOW)
    assert high.price == 4758.0
    assert low.price == 4642.0


def test_short_strangle_emits_range_top_and_bottom():
    # Short 4500p @8 + 4900c @10 → total $18 → range high 4918 / low 4482
    t = _trade(
        _opt(4500, False, "Sell", price=8),
        _opt(4900, True, "Sell", price=10),
    )
    levels = levels_for(t, classify(t))
    high = next(l for l in levels if l.kind == RANGE_HIGH)
    low = next(l for l in levels if l.kind == RANGE_LOW)
    assert high.price == 4918.0
    assert low.price == 4482.0


def test_bull_risk_reversal_emits_target_and_support():
    # Buy 4900c @10 / Sell 4500p @8 → net +2 debit → target 4902, support 4492
    t = _trade(
        _opt(4500, False, "Sell", price=8),
        _opt(4900, True, "Buy", price=10),
    )
    levels = levels_for(t, classify(t))
    bull = next(l for l in levels if l.kind == BULLISH_TARGET)
    sup = next(l for l in levels if l.kind == SUPPORT)
    assert bull.price == 4902.0
    assert sup.price == 4492.0


def test_complex_trade_falls_back_per_leg():
    # 3-leg single expiry → "complex" → per-leg analysis
    t = _trade(
        _opt(4500, False, "Buy", price=10),       # bearish target 4490
        _opt(4700, True, "Sell", price=8),        # resistance     4708
        _opt(4900, True, "Buy", price=4),         # bullish target 4904
    )
    levels = levels_for(t, classify(t))
    by_kind = {l.kind: l.price for l in levels}
    assert by_kind[BEARISH_TARGET] == 4490.0
    assert by_kind[RESISTANCE] == 4708.0
    assert by_kind[BULLISH_TARGET] == 4904.0
