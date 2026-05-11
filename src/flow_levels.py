"""Flow-level math: turn each classified trade into one or more
support / resistance / target levels using the math the user
specified.

User-supplied math (per leg/structure):
- Call:        strike + premium
- Put:         strike - premium
- Call spread: lower strike + net premium
- Put spread:  upper strike - net premium
- Straddle:    strike ± total premium
- Strangle:    call_strike + total premium  AND  put_strike - total premium

Interpretation:
- bought call               -> bullish target
- sold call                 -> resistance
- bought put                -> bearish target / hedge
- sold put                  -> support
- bought straddle/strangle  -> expected_move_high / expected_move_low
- sold straddle/strangle    -> range_high / range_low
- bull risk reversal        -> bullish target + support (sold put)
- bear risk reversal        -> bearish target + resistance (sold call)

For multi-leg structures we don't recognise (calendar / butterfly /
ratio / 4-leg complex), we fall back to a per-leg analysis: each leg
contributes its own level using the basic call/put math.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy import Strategy
from trades import OptionLeg, TradeRecord


# Level "kinds" — vocabulary used by flow_map renderer.
RESISTANCE = "resistance"
SUPPORT = "support"
BULLISH_TARGET = "bullish_target"
BEARISH_TARGET = "bearish_target"
EXPECTED_MOVE_HIGH = "expected_move_high"
EXPECTED_MOVE_LOW = "expected_move_low"
RANGE_HIGH = "range_high"
RANGE_LOW = "range_low"


@dataclass(frozen=True)
class FlowLevel:
    price: float          # the computed price level
    kind: str             # one of the constants above
    strategy_kind: str    # Strategy.kind
    description: str      # human-readable note for the renderer
    weight: int           # qty × premium-per-contract — used for ranking
    expiry_code: str      # primary expiry of the trade
    time_ct: str          # for traceability in the report
    venue: str            # "BLOCK" | "GTB"


def _weight(qty: int, price: float) -> int:
    """Premium notional ≈ qty × premium × 100 oz (relative ranking only)."""
    return int(round(qty * max(price, 0.0) * 100))


def levels_for(trade: TradeRecord, strategy: Strategy) -> list[FlowLevel]:
    """Return the list of FlowLevels implied by ``trade`` + ``strategy``."""
    legs = list(strategy.primary_legs)
    if not legs:
        return []

    venue = trade.venue
    time_ct = trade.time_ct
    expiry = trade.primary_expiry

    def lvl(price: float, kind: str, desc: str, weight: int) -> FlowLevel:
        return FlowLevel(
            price=round(price, 2), kind=kind, strategy_kind=strategy.kind,
            description=desc, weight=weight,
            expiry_code=expiry, time_ct=time_ct, venue=venue)

    sk = strategy.kind

    # ---- Outright legs ----
    if sk == "call_long":
        l = legs[0]
        return [lvl(l.strike + l.price, BULLISH_TARGET,
                    f"покупка {l.qty}× {l.strike:g}c @ {l.price:.2f} → "
                    f"безубыток {l.strike + l.price:.2f}",
                    _weight(l.qty, l.price))]
    if sk == "call_short":
        l = legs[0]
        return [lvl(l.strike + l.price, RESISTANCE,
                    f"продажа {l.qty}× {l.strike:g}c @ {l.price:.2f} → "
                    f"сопротивление {l.strike + l.price:.2f}",
                    _weight(l.qty, l.price))]
    if sk == "put_long":
        l = legs[0]
        return [lvl(l.strike - l.price, BEARISH_TARGET,
                    f"покупка {l.qty}× {l.strike:g}p @ {l.price:.2f} → "
                    f"безубыток {l.strike - l.price:.2f}",
                    _weight(l.qty, l.price))]
    if sk == "put_short":
        l = legs[0]
        return [lvl(l.strike - l.price, SUPPORT,
                    f"продажа {l.qty}× {l.strike:g}p @ {l.price:.2f} → "
                    f"поддержка {l.strike - l.price:.2f}",
                    _weight(l.qty, l.price))]

    # ---- Vertical spreads ----
    if sk == "call_vertical_bull":
        lo, hi = legs                      # primary_legs ordered low/high
        net_debit = abs(lo.price - hi.price)
        target = lo.strike + net_debit
        # Weight by smaller leg's contracts (the spread's actual size).
        wt = _weight(min(lo.qty, hi.qty), net_debit)
        return [lvl(target, BULLISH_TARGET,
                    f"бычий колл-спред {lo.strike:g}/{hi.strike:g} дебет "
                    f"{net_debit:.2f} → безубыток {target:.2f}", wt)]
    if sk == "call_vertical_bear":
        lo, hi = legs
        net_credit = abs(lo.price - hi.price)
        level = lo.strike + net_credit
        wt = _weight(min(lo.qty, hi.qty), net_credit)
        return [lvl(level, RESISTANCE,
                    f"медвежий колл-спред {lo.strike:g}/{hi.strike:g} кредит "
                    f"{net_credit:.2f} → сопротивление {level:.2f}", wt)]
    if sk == "put_vertical_bear":
        lo, hi = legs
        net_debit = abs(hi.price - lo.price)
        target = hi.strike - net_debit
        wt = _weight(min(lo.qty, hi.qty), net_debit)
        return [lvl(target, BEARISH_TARGET,
                    f"медвежий пут-спред {hi.strike:g}/{lo.strike:g} дебет "
                    f"{net_debit:.2f} → безубыток {target:.2f}", wt)]
    if sk == "put_vertical_bull":
        lo, hi = legs
        net_credit = abs(hi.price - lo.price)
        level = hi.strike - net_credit
        wt = _weight(min(lo.qty, hi.qty), net_credit)
        return [lvl(level, SUPPORT,
                    f"бычий пут-спред {hi.strike:g}/{lo.strike:g} кредит "
                    f"{net_credit:.2f} → поддержка {level:.2f}", wt)]

    # ---- Straddles / strangles ----
    if sk == "straddle_long":
        a, b = legs
        total = a.price + b.price
        s = a.strike
        wt = _weight(min(a.qty, b.qty), total)
        return [
            lvl(s + total, EXPECTED_MOVE_HIGH,
                f"длинный стрэддл {s:g} за {total:.2f} → ОД ±{total:.2f}", wt),
            lvl(s - total, EXPECTED_MOVE_LOW,
                f"длинный стрэддл {s:g} за {total:.2f} → ОД ±{total:.2f}", wt),
        ]
    if sk == "straddle_short":
        a, b = legs
        total = a.price + b.price
        s = a.strike
        wt = _weight(min(a.qty, b.qty), total)
        return [
            lvl(s + total, RANGE_HIGH,
                f"короткий стрэддл {s:g} за {total:.2f} → диапазон "
                f"{s-total:.0f}-{s+total:.0f}", wt),
            lvl(s - total, RANGE_LOW,
                f"короткий стрэддл {s:g} за {total:.2f} → диапазон "
                f"{s-total:.0f}-{s+total:.0f}", wt),
        ]
    if sk == "strangle_long":
        put_leg, call_leg = legs           # primary_legs ordered put, call
        total = put_leg.price + call_leg.price
        wt = _weight(min(put_leg.qty, call_leg.qty), total)
        return [
            lvl(call_leg.strike + total, EXPECTED_MOVE_HIGH,
                f"длинный стрэнгл {put_leg.strike:g}p/{call_leg.strike:g}c "
                f"за {total:.2f} → пробой {call_leg.strike+total:.2f}",
                wt),
            lvl(put_leg.strike - total, EXPECTED_MOVE_LOW,
                f"длинный стрэнгл {put_leg.strike:g}p/{call_leg.strike:g}c "
                f"за {total:.2f} → пробой {put_leg.strike-total:.2f}",
                wt),
        ]
    if sk == "strangle_short":
        put_leg, call_leg = legs
        total = put_leg.price + call_leg.price
        wt = _weight(min(put_leg.qty, call_leg.qty), total)
        return [
            lvl(call_leg.strike + total, RANGE_HIGH,
                f"короткий стрэнгл {put_leg.strike:g}p/{call_leg.strike:g}c "
                f"за {total:.2f} → диапазон "
                f"{put_leg.strike-total:.0f}-{call_leg.strike+total:.0f}", wt),
            lvl(put_leg.strike - total, RANGE_LOW,
                f"короткий стрэнгл {put_leg.strike:g}p/{call_leg.strike:g}c "
                f"за {total:.2f} → диапазон "
                f"{put_leg.strike-total:.0f}-{call_leg.strike+total:.0f}", wt),
        ]

    # ---- Risk reversals ----
    if sk == "risk_reversal_bull":
        put_leg, call_leg = legs           # buy call, sell put
        net = call_leg.price - put_leg.price   # >0 = debit, <0 = credit
        target = call_leg.strike + max(net, 0.0)
        wt_c = _weight(call_leg.qty, call_leg.price)
        wt_p = _weight(put_leg.qty, put_leg.price)
        return [
            lvl(target, BULLISH_TARGET,
                f"бычий risk reversal: покупка {call_leg.strike:g}c / "
                f"продажа {put_leg.strike:g}p (нетто {net:+.2f})", wt_c),
            lvl(put_leg.strike - put_leg.price, SUPPORT,
                f"бычий RR — проданный пут → поддержка "
                f"{put_leg.strike - put_leg.price:.2f}", wt_p),
        ]
    if sk == "risk_reversal_bear":
        put_leg, call_leg = legs           # buy put, sell call
        net = put_leg.price - call_leg.price
        target = put_leg.strike - max(net, 0.0)
        wt_p = _weight(put_leg.qty, put_leg.price)
        wt_c = _weight(call_leg.qty, call_leg.price)
        return [
            lvl(target, BEARISH_TARGET,
                f"медвежий risk reversal: покупка {put_leg.strike:g}p / "
                f"продажа {call_leg.strike:g}c (нетто {net:+.2f})", wt_p),
            lvl(call_leg.strike + call_leg.price, RESISTANCE,
                f"медвежий RR — проданный колл → сопротивление "
                f"{call_leg.strike + call_leg.price:.2f}", wt_c),
        ]

    # ---- Fallback: per-leg analysis for complex / calendar / 3+ leg ----
    out: list[FlowLevel] = []
    for l in legs:
        out.extend(_per_leg_levels(l, strategy.kind, time_ct, venue, expiry))
    return out


def _per_leg_levels(l: OptionLeg, sk: str, time_ct: str, venue: str,
                    expiry: str) -> list[FlowLevel]:
    """Per-leg fallback for multi-leg / calendar trades."""
    wt = _weight(l.qty, l.price)
    if l.is_call and l.side == "Buy":
        return [FlowLevel(
            price=round(l.strike + l.price, 2), kind=BULLISH_TARGET,
            strategy_kind=sk,
            description=(f"нога лонг {l.qty}× {l.strike:g}c @ "
                         f"{l.price:.2f}"),
            weight=wt, expiry_code=expiry, time_ct=time_ct, venue=venue)]
    if l.is_call and l.side == "Sell":
        return [FlowLevel(
            price=round(l.strike + l.price, 2), kind=RESISTANCE,
            strategy_kind=sk,
            description=(f"нога шорт {l.qty}× {l.strike:g}c @ "
                         f"{l.price:.2f}"),
            weight=wt, expiry_code=expiry, time_ct=time_ct, venue=venue)]
    if (not l.is_call) and l.side == "Buy":
        return [FlowLevel(
            price=round(l.strike - l.price, 2), kind=BEARISH_TARGET,
            strategy_kind=sk,
            description=(f"нога лонг {l.qty}× {l.strike:g}p @ "
                         f"{l.price:.2f}"),
            weight=wt, expiry_code=expiry, time_ct=time_ct, venue=venue)]
    return [FlowLevel(
        price=round(l.strike - l.price, 2), kind=SUPPORT,
        strategy_kind=sk,
        description=(f"нога шорт {l.qty}× {l.strike:g}p @ "
                     f"{l.price:.2f}"),
        weight=wt, expiry_code=expiry, time_ct=time_ct, venue=venue)]
