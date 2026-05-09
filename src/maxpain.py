"""Max Pain calculation and OI walls extraction.

Max Pain formula:
    Pain(K) = Sum_i [ max(K - K_i, 0) * OI_call_i ]
            + Sum_i [ max(K_i - K, 0) * OI_put_i  ]

The strike K that minimises Pain(K) is the "Max Pain" level.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrikeRow:
    strike: float
    call_oi: int
    put_oi: int
    call_oi_change: int = 0  # delta vs previous EOD
    put_oi_change: int = 0


def max_pain(rows: list[StrikeRow]) -> tuple[float, dict[float, float]]:
    """Return (max_pain_strike, pain_by_strike_dict).

    Searches over the universe of listed strikes (ie K_i for some i).
    For OG monthly options this is the standard convention.
    """
    if not rows:
        raise ValueError("rows is empty")
    strikes = sorted({r.strike for r in rows})
    pain: dict[float, float] = {}
    for K in strikes:
        total = 0.0
        for r in rows:
            if r.strike < K:
                # ITM call
                total += (K - r.strike) * r.call_oi
            elif r.strike > K:
                # ITM put
                total += (r.strike - K) * r.put_oi
        pain[K] = total
    mp = min(pain, key=lambda k: pain[k])
    return mp, pain


def call_walls(rows: list[StrikeRow], n: int = 3) -> list[StrikeRow]:
    return sorted(rows, key=lambda r: -r.call_oi)[:n]


def put_walls(rows: list[StrikeRow], n: int = 3) -> list[StrikeRow]:
    return sorted(rows, key=lambda r: -r.put_oi)[:n]


def biggest_call_oi_changes(rows: list[StrikeRow], n: int = 3) -> list[StrikeRow]:
    return sorted(rows, key=lambda r: -abs(r.call_oi_change))[:n]


def biggest_put_oi_changes(rows: list[StrikeRow], n: int = 3) -> list[StrikeRow]:
    return sorted(rows, key=lambda r: -abs(r.put_oi_change))[:n]
