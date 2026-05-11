"""Flow-levels map: aggregate per-trade FlowLevels into a tradable
list of support / resistance / targets / expected-move levels and
render it as Markdown.

Aggregation strategy
--------------------
We bucket each level into one of four buckets:

- ``resistance``       (RESISTANCE, EXPECTED_MOVE_HIGH, RANGE_HIGH)
- ``support``          (SUPPORT, EXPECTED_MOVE_LOW, RANGE_LOW)
- ``bullish_target``   (BULLISH_TARGET)
- ``bearish_target``   (BEARISH_TARGET)

Within each bucket we group levels whose prices fall inside a small
window (``$5`` for gold by default) and sum their weights — so that a
$4,800 resistance reinforced by three different trades shows up as one
fat level, not three near-duplicates.

The renderer emits a Markdown section ready to paste into the daily
report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from flow_levels import (
    BEARISH_TARGET,
    BULLISH_TARGET,
    EXPECTED_MOVE_HIGH,
    EXPECTED_MOVE_LOW,
    FlowLevel,
    RANGE_HIGH,
    RANGE_LOW,
    RESISTANCE,
    SUPPORT,
)


_RESISTANCE_KINDS = {RESISTANCE, EXPECTED_MOVE_HIGH, RANGE_HIGH}
_SUPPORT_KINDS = {SUPPORT, EXPECTED_MOVE_LOW, RANGE_LOW}

# Strategy kinds where ``flow_levels.levels_for`` falls back to per-leg
# analysis (e.g. each leg of a 4-leg structure becomes its own level).
# These are isolated to a "~per-leg" subsection in the renderer so they
# don't pollute the primary flow map.
_PER_LEG_STRATEGY_KINDS = {"complex", "calendar"}


def is_per_leg(level: FlowLevel) -> bool:
    """True if ``level`` came from per-leg fallback (3+ leg / calendar)."""
    return level.strategy_kind in _PER_LEG_STRATEGY_KINDS


@dataclass
class AggregatedLevel:
    price: float           # midpoint of the cluster
    bucket: str            # "resistance" | "support" | "bullish_target" | "bearish_target"
    total_weight: int      # sum of contributing levels' weights
    contributing: list[FlowLevel]

    @property
    def venues(self) -> set[str]:
        return {l.venue for l in self.contributing}


def bucket_for(level: FlowLevel) -> str:
    if level.kind in _RESISTANCE_KINDS:
        return "resistance"
    if level.kind in _SUPPORT_KINDS:
        return "support"
    if level.kind == BULLISH_TARGET:
        return "bullish_target"
    if level.kind == BEARISH_TARGET:
        return "bearish_target"
    return "other"


def cluster(levels: Iterable[FlowLevel],
            window: float = 5.0) -> list[AggregatedLevel]:
    """Cluster levels by (bucket, price) — group prices within ``window``.

    For gold (settlement around $4,700) a $5 window is roughly 0.1%, so
    e.g. 4,799 and 4,801 collapse but 4,800 and 4,820 stay separate.

    Returns clusters sorted by total_weight descending.
    """
    by_bucket: dict[str, list[FlowLevel]] = {
        "resistance": [], "support": [],
        "bullish_target": [], "bearish_target": [], "other": [],
    }
    for l in levels:
        by_bucket[bucket_for(l)].append(l)

    out: list[AggregatedLevel] = []
    for bucket, items in by_bucket.items():
        if bucket == "other" or not items:
            continue
        # Sort by price then sweep with a `window`-wide bucket.
        items.sort(key=lambda x: x.price)
        i = 0
        while i < len(items):
            j = i + 1
            while j < len(items) and (items[j].price - items[i].price) <= window:
                j += 1
            cluster_items = items[i:j]
            mid = sum(c.price for c in cluster_items) / len(cluster_items)
            tw = sum(c.weight for c in cluster_items)
            out.append(AggregatedLevel(
                price=round(mid, 2), bucket=bucket,
                total_weight=tw, contributing=cluster_items))
            i = j

    out.sort(key=lambda a: -a.total_weight)
    return out


# ----------------------------------------------------------------------------
# Markdown rendering
# ----------------------------------------------------------------------------


def _fmt_price(p: float) -> str:
    return f"${p:,.2f}" if (p % 1) else f"${p:,.0f}"


def _fmt_weight(w: int) -> str:
    """Compact human weight (K / M)."""
    if w >= 1_000_000:
        return f"${w/1_000_000:.1f}M"
    if w >= 1_000:
        return f"${w/1_000:.0f}K"
    return f"${w}"


def _short_desc(level: FlowLevel) -> str:
    return level.description


def _bucket_clusters(clusters: list[AggregatedLevel],
                     *, spot: Optional[float]) -> dict[str, list[AggregatedLevel]]:
    """Group + sort clusters by bucket — closest-to-spot first when known."""
    by_bucket: dict[str, list[AggregatedLevel]] = {
        "resistance": [], "support": [],
        "bullish_target": [], "bearish_target": [],
    }
    for c in clusters:
        if c.bucket in by_bucket:
            by_bucket[c.bucket].append(c)

    if spot is not None:
        by_bucket["resistance"].sort(
            key=lambda a: (abs(a.price - spot) if a.price >= spot else 1e9))
        by_bucket["bullish_target"].sort(
            key=lambda a: (a.price - spot) if a.price >= spot else 1e9)
        by_bucket["support"].sort(
            key=lambda a: (abs(spot - a.price) if a.price <= spot else 1e9))
        by_bucket["bearish_target"].sort(
            key=lambda a: (spot - a.price) if a.price <= spot else 1e9)
    else:
        by_bucket["resistance"].sort(key=lambda a: a.price)
        by_bucket["bullish_target"].sort(key=lambda a: a.price)
        by_bucket["support"].sort(key=lambda a: -a.price)
        by_bucket["bearish_target"].sort(key=lambda a: -a.price)
    return by_bucket


def render_flow_map(levels: list[FlowLevel],
                    *,
                    spot: Optional[float] = None,
                    top_n: int = 5,
                    window: float = 5.0) -> str:
    """Render aggregated levels as a Markdown sub-section.

    ``spot`` is included so we can sort levels above/below current price
    and annotate each with its distance.

    Levels coming from per-leg fallback (3+ leg / calendar trades — see
    ``flow_levels`` for context) are surfaced in a dedicated "~per-leg"
    subsection so they don't dominate the primary buckets.
    """
    if not levels:
        return ("_Нет уровней из опционного потока — не удалось интерпретировать "
                "ни одной сделки._")

    primary_levels = [l for l in levels if not is_per_leg(l)]
    perleg_levels = [l for l in levels if is_per_leg(l)]

    primary_clusters = cluster(primary_levels, window=window)
    perleg_clusters = cluster(perleg_levels, window=window)

    if not primary_clusters and not perleg_clusters:
        return ("_Нет уровней из опционного потока — все сделки отфильтрованы "
                "как complex / неподдерживаемые._")

    primary_by_bucket = _bucket_clusters(primary_clusters, spot=spot)
    perleg_by_bucket = _bucket_clusters(perleg_clusters, spot=spot)

    lines: list[str] = []

    def section(title: str, items: list[AggregatedLevel]) -> None:
        lines.append(f"**{title}**")
        if not items:
            lines.append("_(нет)_")
            lines.append("")
            return
        for c in items[:top_n]:
            dist = ""
            if spot is not None:
                d = c.price - spot
                dist = f"  ({d:+,.0f})"
            tag = f"[{', '.join(sorted(c.venues))}]" if c.venues else ""
            n = len(c.contributing)
            lines.append(
                f"- **{_fmt_price(c.price)}**{dist}  •  вес "
                f"{_fmt_weight(c.total_weight)}  •  "
                f"{n} {_plural_trades(n)} {tag}")
            for l in c.contributing[:3]:
                lines.append(f"    - _{l.time_ct} CT — {_short_desc(l)}_")
            if len(c.contributing) > 3:
                lines.append(f"    - _… ещё +{len(c.contributing)-3}_")
        lines.append("")

    if primary_clusters:
        section("Сопротивление / верх диапазона",
                primary_by_bucket["resistance"])
        section("Поддержка / низ диапазона",
                primary_by_bucket["support"])
        section("Бычьи цели", primary_by_bucket["bullish_target"])
        section("Медвежьи цели", primary_by_bucket["bearish_target"])

    if perleg_clusters:
        lines.append(
            "**~по ногам** _(отдельные ноги многоножных / календарных "
            "структур \u2014 справочно; ноги взаимодействуют между собой)_")
        lines.append("")
        section("~ Сопротивление", perleg_by_bucket["resistance"])
        section("~ Поддержка", perleg_by_bucket["support"])
        section("~ Бычьи цели", perleg_by_bucket["bullish_target"])
        section("~ Медвежьи цели", perleg_by_bucket["bearish_target"])

    return "\n".join(lines).rstrip() + "\n"


def _plural_trades(n: int) -> str:
    """Russian plural form for the noun ‘сделка’."""
    n_abs = abs(n) % 100
    if 11 <= n_abs <= 14:
        return "сделок"
    mod10 = n_abs % 10
    if mod10 == 1:
        return "сделка"
    if 2 <= mod10 <= 4:
        return "сделки"
    return "сделок"


def render_expected_move(levels: list[FlowLevel]) -> str:
    """Render a one-liner about expected move based on long straddles /
    strangles.  Returns empty string if no relevant trades.
    """
    em_high = [l for l in levels if l.kind == EXPECTED_MOVE_HIGH]
    em_low = [l for l in levels if l.kind == EXPECTED_MOVE_LOW]
    if not em_high and not em_low:
        return ""
    parts = []
    if em_high:
        biggest = max(em_high, key=lambda l: l.weight)
        parts.append(f"верх {biggest.price:,.2f}")
    if em_low:
        biggest = max(em_low, key=lambda l: l.weight)
        parts.append(f"низ {biggest.price:,.2f}")
    return ("Ожидаемое движение по длинным vol-сделкам: "
            + " / ".join(parts) + ".")
