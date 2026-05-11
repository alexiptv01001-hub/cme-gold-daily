"""Heuristic buy/sell classifier for option trades that lack an explicit
"side" column.

Block-trade publication on CME publishes the customer side directly
(``"Buy"``/``"Sell"`` on every leg).  Electronic-tape data sometimes
does not — only the trade price and the bid/ask at the moment of the
trade.  In that case we infer the side using the standard
"trade-at-ask = bought premium / trade-at-bid = sold premium" rule.

This module is also useful for sanity-checking explicit-side data —
callers can run ``classify(price, bid, ask)`` and compare against the
explicit side column to flag suspicious rows.

Caller responsibility: pass the OPTION quote (premium per option), not
the underlying price.  ``bid`` ≤ ``ask`` is required; both must be
non-negative.
"""
from __future__ import annotations

from typing import Literal, Optional

Side = Literal["Buy", "Sell", "Mid"]


def classify(price: float, bid: Optional[float], ask: Optional[float],
             *,
             tolerance: float = 0.20) -> Side:
    """Classify a trade by proximity to bid/ask.

    Returns:
        "Buy"  if price is in the upper ``tolerance`` of the bid/ask range
                  (customer paid the ask → bought premium)
        "Sell" if price is in the lower ``tolerance`` of the range
                  (customer hit the bid → sold premium)
        "Mid"  otherwise

    If bid/ask is missing or zero-width the function returns "Mid" — we
    cannot tell.

    The default ``tolerance=0.20`` means any trade within 20 % of the
    bid (or ask) counts as a sell (or buy).  Tighten to 0.05 for more
    conservative inference.
    """
    if bid is None or ask is None:
        return "Mid"
    if ask < bid:
        # malformed feed — assume Mid
        return "Mid"
    spread = ask - bid
    if spread <= 0:
        return "Mid"
    pos = (price - bid) / spread        # 0 = bid, 1 = ask
    if pos >= 1.0 - tolerance:
        return "Buy"
    if pos <= tolerance:
        return "Sell"
    return "Mid"
