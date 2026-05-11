"""Strategy classifier for option trades.

Given a ``TradeRecord``, identify the option strategy (long/short call,
vertical spread, straddle, strangle, risk reversal, …) and the
directional bias.

Bias semantics
--------------
- bullish:           expects underlying up
- bearish:           expects underlying down
- neutral_breakout:  expects a large move in either direction (long vol)
- neutral_range:     expects underlying to stay in a range (short vol)
- unknown:           multi-leg / multi-expiry trade we can't classify

The classifier ignores futures hedge legs — those are tactical delta
hedges that don't change the strategy's directional view.
"""
from __future__ import annotations

from dataclasses import dataclass

from trades import OptionLeg, TradeRecord


@dataclass(frozen=True)
class Strategy:
    kind: str             # "call_long", "put_vertical_bear", …
    direction: str        # "bullish" | "bearish" | "neutral_breakout" | "neutral_range" | "unknown"
    description: str
    primary_legs: list[OptionLeg]


def _single_expiry(legs: list[OptionLeg]) -> bool:
    return len({l.expiry_code for l in legs}) == 1


def classify(trade: TradeRecord) -> Strategy:
    """Return the recognised strategy for ``trade`` (or 'complex')."""
    legs = list(trade.option_legs)

    if not legs:
        return Strategy(
            kind="complex", direction="unknown",
            description="no option legs", primary_legs=[])

    # Multi-expiry → calendar / diagonal — we don't try to classify these.
    if not _single_expiry(legs):
        n_exp = len({l.expiry_code for l in legs})
        return Strategy(
            kind="calendar", direction="unknown",
            description=f"{len(legs)} legs across {n_exp} expiries",
            primary_legs=legs)

    # ---- Single expiry ----
    if len(legs) == 1:
        return _classify_outright(legs[0])

    if len(legs) == 2:
        s = _classify_two_leg(legs)
        if s is not None:
            return s

    # 3+ legs single expiry → fall back to "complex" but keep the legs so
    # the flow-levels pass can use per-leg analysis as a fallback.
    return Strategy(
        kind="complex", direction="unknown",
        description=f"{len(legs)}-leg structure", primary_legs=legs)


def _classify_outright(l: OptionLeg) -> Strategy:
    if l.is_call and l.side == "Buy":
        return Strategy(kind="call_long", direction="bullish",
                        description=f"long {l.strike:g} call", primary_legs=[l])
    if l.is_call and l.side == "Sell":
        return Strategy(kind="call_short", direction="bearish",
                        description=f"short {l.strike:g} call", primary_legs=[l])
    if (not l.is_call) and l.side == "Buy":
        return Strategy(kind="put_long", direction="bearish",
                        description=f"long {l.strike:g} put", primary_legs=[l])
    return Strategy(kind="put_short", direction="bullish",
                    description=f"short {l.strike:g} put", primary_legs=[l])


def _classify_two_leg(legs: list[OptionLeg]) -> Strategy | None:
    a, b = legs

    # Vertical spread: same type, different strikes, opposite sides.
    if a.is_call == b.is_call and a.strike != b.strike and a.side != b.side:
        lo, hi = (a, b) if a.strike < b.strike else (b, a)
        if a.is_call:
            if lo.side == "Buy":
                # bull call spread (long lower / short higher)
                return Strategy(
                    kind="call_vertical_bull", direction="bullish",
                    description=(f"bull call spread {lo.strike:g}/{hi.strike:g}"),
                    primary_legs=[lo, hi])
            return Strategy(
                kind="call_vertical_bear", direction="bearish",
                description=(f"bear call spread {lo.strike:g}/{hi.strike:g}"),
                primary_legs=[lo, hi])
        # Put vertical
        if hi.side == "Buy":
            # bear put spread (long higher / short lower)
            return Strategy(
                kind="put_vertical_bear", direction="bearish",
                description=(f"bear put spread {hi.strike:g}/{lo.strike:g}"),
                primary_legs=[lo, hi])
        return Strategy(
            kind="put_vertical_bull", direction="bullish",
            description=(f"bull put spread {hi.strike:g}/{lo.strike:g}"),
            primary_legs=[lo, hi])

    # Straddle: call + put, same strike, same side.
    if a.is_call != b.is_call and a.strike == b.strike and a.side == b.side:
        if a.side == "Buy":
            return Strategy(
                kind="straddle_long", direction="neutral_breakout",
                description=f"long {a.strike:g} straddle",
                primary_legs=[a, b])
        return Strategy(
            kind="straddle_short", direction="neutral_range",
            description=f"short {a.strike:g} straddle",
            primary_legs=[a, b])

    # Strangle: call + put, different strikes, same side.
    if a.is_call != b.is_call and a.strike != b.strike and a.side == b.side:
        call_leg = a if a.is_call else b
        put_leg = b if a.is_call else a
        if a.side == "Buy":
            return Strategy(
                kind="strangle_long", direction="neutral_breakout",
                description=(f"long {put_leg.strike:g}p / "
                             f"{call_leg.strike:g}c strangle"),
                primary_legs=[put_leg, call_leg])
        return Strategy(
            kind="strangle_short", direction="neutral_range",
            description=(f"short {put_leg.strike:g}p / "
                         f"{call_leg.strike:g}c strangle"),
            primary_legs=[put_leg, call_leg])

    # Risk reversal: call + put, opposite sides.
    if a.is_call != b.is_call and a.side != b.side:
        call_leg = a if a.is_call else b
        put_leg = b if a.is_call else a
        if call_leg.side == "Buy" and put_leg.side == "Sell":
            return Strategy(
                kind="risk_reversal_bull", direction="bullish",
                description=(f"buy {call_leg.strike:g}c / "
                             f"sell {put_leg.strike:g}p"),
                primary_legs=[put_leg, call_leg])
        if call_leg.side == "Sell" and put_leg.side == "Buy":
            return Strategy(
                kind="risk_reversal_bear", direction="bearish",
                description=(f"buy {put_leg.strike:g}p / "
                             f"sell {call_leg.strike:g}c"),
                primary_legs=[put_leg, call_leg])

    return None
