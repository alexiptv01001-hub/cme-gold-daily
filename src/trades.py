"""Common data model for option trades — used by block-trade scraper and
the QuikStrike Globex Trade Browser scraper.

We unify both data sources behind a single ``TradeRecord`` so that the
strategy classifier and flow-level math don't need to know where the
trade came from.

A TradeRecord has zero-or-more ``OptionLeg`` and zero-or-more
``FuturesLeg``.  Outright option trades have one option leg and no
futures legs; spreads have multiple option legs; many institutional
spreads also include hedging futures legs.

The adapter `from_block_trade()` converts the existing
``block_trades.BlockTrade`` shape into a ``TradeRecord``.  When the
QuikStrike electronic-trade scraper lands, it will populate the same
``TradeRecord`` shape.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class OptionLeg:
    """One option contract in a trade.

    ``side`` is the BUYER's perspective: "Buy" if the customer paid the
    premium for this leg, "Sell" if they received it.  ``qty`` is always
    positive — direction is encoded in ``side``.
    """
    expiry_code: str       # "OGM6"
    underlying_code: str   # "GCM6" — the underlying GC future
    is_call: bool
    strike: float
    side: str              # "Buy" | "Sell"
    qty: int               # always positive
    price: float           # premium per option (in $/oz for GC)


@dataclass(frozen=True)
class FuturesLeg:
    """One outright futures contract leg of a multi-leg trade."""
    contract_code: str     # "GCM6"
    side: str              # "Buy" | "Sell"
    qty: int               # always positive
    price: Optional[float] = None  # block report sometimes omits price


@dataclass
class TradeRecord:
    """A single block or electronic trade — possibly multi-leg."""
    venue: str             # "BLOCK" or "GTB"
    time_ct: str           # original CT string from CME ("11:29:29 AM")
    time_utc: Optional[datetime] = None  # parsed UTC datetime if available
    trade_type: str = ""   # "Spread" / "Strip" / "Future" / "Option" / "Outright"
    option_legs: list[OptionLeg] = field(default_factory=list)
    futures_legs: list[FuturesLeg] = field(default_factory=list)
    net_price: Optional[float] = None
    spread_qty: Optional[int] = None
    spot_at_trade: Optional[float] = None  # GC futures spot at time_utc

    @property
    def primary_expiry(self) -> str:
        """Most-common expiry code across the option legs (or '' if none)."""
        if not self.option_legs:
            return ""
        return Counter(l.expiry_code for l in self.option_legs).most_common(1)[0][0]

    @property
    def total_option_qty(self) -> int:
        return sum(l.qty for l in self.option_legs)

    @property
    def gross_premium(self) -> float:
        """Σ qty × price across option legs (in option-quote units).

        Treat as a relative weight, not as an exact $ value (CME quotes
        gold options in $/oz × 100 oz/contract — use this only for
        ranking, not P/L).
        """
        return sum(l.qty * l.price for l in self.option_legs)


# ----------------------------------------------------------------------------
# Adapters
# ----------------------------------------------------------------------------


def _underlying_for(expiry_code: str) -> str:
    """Infer the underlying GC future code from an OG option code.

    OG monthly options expire into the same-month GC future:
        OGM6 -> GCM6,  OGM26 -> GCM26 (forms vary).
    Weekly options use prefixes 1OG..5OG; their underlying is the next
    monthly GC.  We approximate by replacing the leading 'OG' with 'GC'
    after stripping the leading digit (if any).
    """
    s = expiry_code.upper()
    if s.startswith(("1OG", "2OG", "3OG", "4OG", "5OG")):
        s = s[1:]
    if s.startswith("OG"):
        return "GC" + s[2:]
    return s  # already a futures code or unknown — leave as is


def from_block_trade(bt) -> TradeRecord:
    """Convert a ``block_trades.BlockTrade`` into a ``TradeRecord``."""
    option_legs: list[OptionLeg] = []
    futures_legs: list[FuturesLeg] = []
    for leg in bt.legs:
        product = (leg.product or "").lower()
        is_future = ("future" in product) and ("option" not in product)
        if is_future:
            futures_legs.append(FuturesLeg(
                contract_code=leg.sym, side=leg.side, qty=leg.qty,
                price=leg.price or None,
            ))
            continue
        cp = (leg.cp_strike or "").strip()
        if not cp or cp[0] not in ("C", "P"):
            continue
        is_call = cp[0] == "C"
        try:
            strike = float(cp[1:])
        except ValueError:
            continue
        option_legs.append(OptionLeg(
            expiry_code=leg.sym,
            underlying_code=_underlying_for(leg.sym),
            is_call=is_call, strike=strike, side=leg.side,
            qty=leg.qty, price=leg.price,
        ))
    return TradeRecord(
        venue="BLOCK",
        time_ct=bt.time_ct,
        trade_type=bt.trade_type or "",
        option_legs=option_legs,
        futures_legs=futures_legs,
        net_price=bt.net_price,
        spread_qty=bt.spread_qty,
    )
