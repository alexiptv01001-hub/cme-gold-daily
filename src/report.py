"""Markdown report formatter for the daily CME gold swing-trading report."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from futures import FutureSettle
from maxpain import StrikeRow, max_pain, call_walls, put_walls


def _fmt_int(n: Optional[int]) -> str:
    return f"{n:,}" if n is not None else "—"


def _fmt_money(x: Optional[float]) -> str:
    return f"${x:,.1f}" if x is not None else "—"


def _signed(d: Optional[float]) -> str:
    if d is None:
        return ""
    return f"({'+' if d>=0 else ''}{d:,.0f})"


def render_report(
    *,
    trade_date: str,
    front: FutureSettle,
    expiry_label: str,
    rows: list[StrikeRow],
    blocks_md: str = "",
    most_active: list[tuple[float, str, int]] | None = None,  # (strike, "C"/"P", volume)
    flow_map_md: str = "",
    expected_move_md: str = "",
    notes: Optional[list[str]] = None,
) -> str:
    """Render full Markdown report.

    `front`     : the active gold futures contract (used for current price).
    `expiry_label`: e.g. "OG JUN 2026 (monthly)".
    `rows`      : strike-level OI for the chosen options expiry.
    `blocks_md` : pre-rendered Markdown for the institutional-flow section
                  (typically `block_trades.render_blocks_md(...)`).
    `most_active`: (strike, side, volume) sorted desc.
    `flow_map_md`: pre-rendered Markdown for the flow-levels-map section
                  (from ``flow_map.render_flow_map(...)``).
    `expected_move_md`: optional one-liner describing expected-move from
                  long-vol trades (from ``flow_map.render_expected_move``).
    """
    most_active = most_active or []
    px = front.settle if front.settle is not None else front.last
    mp, _ = max_pain(rows)
    cw = call_walls(rows, n=3)
    pw = put_walls(rows, n=3)

    lines: list[str] = []
    lines.append(f"# Gold (GC) — Daily Swing-Trading Levels")
    lines.append(f"_Trade date: **{trade_date}** • generated "
                 f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")

    # ---- Price ----
    lines.append("## Price (front-month GC)")
    lines.append(f"- Contract: **{front.month}**")
    lines.append(f"- Settlement: **{_fmt_money(front.settle)}**  "
                 f"(last {_fmt_money(front.last)}, change {_signed(front.change)})")
    lines.append(f"- Volume: {_fmt_int(front.volume)}  •  "
                 f"OI: {_fmt_int(front.open_interest)}")
    lines.append("")

    # ---- Max Pain ----
    lines.append(f"## Max Pain — {expiry_label}")
    lines.append(f"- **Max Pain strike:** ${mp:,.0f}")
    if px is not None:
        delta = mp - px
        bias = ("market wants to **drift down** to max pain"
                if delta < -1 else "market wants to **drift up** to max pain"
                if delta > 1 else "price is right on max pain")
        lines.append(f"- Distance from price: {delta:+,.0f} pts ({bias})")
    lines.append("")

    # ---- Call walls ----
    lines.append("## Resistance — Call walls (top-3 by OI)")
    lines.append("| Strike | Call OI | ΔOI |")
    lines.append("|---:|---:|---:|")
    for r in cw:
        lines.append(f"| ${r.strike:,.0f} | {_fmt_int(r.call_oi)} "
                     f"| {_signed(r.call_oi_change)} |")
    lines.append("")

    # ---- Put walls ----
    lines.append("## Support — Put walls (top-3 by OI)")
    lines.append("| Strike | Put OI | ΔOI |")
    lines.append("|---:|---:|---:|")
    for r in pw:
        lines.append(f"| ${r.strike:,.0f} | {_fmt_int(r.put_oi)} "
                     f"| {_signed(r.put_oi_change)} |")
    lines.append("")

    # ---- Most Active ----
    if most_active:
        lines.append("## Most Active Strikes (by volume yesterday)")
        lines.append("| Strike | Side | Volume |")
        lines.append("|---:|:---:|---:|")
        for k, side, vol in most_active[:5]:
            lines.append(f"| ${k:,.0f} | {side} | {_fmt_int(vol)} |")
        lines.append("")

    # ---- Block trades (institutional flow from Globex Trade Browser) ----
    lines.append("## Institutional flow \u2014 Globex Trade Browser (top block trades)")
    lines.append(blocks_md.strip()
                 or "_No notable gold block trades reported today._")
    lines.append("")

    # ---- Flow Levels Map (computed from option-flow premium math) ----
    lines.append("## Flow Levels Map (option-flow derived levels)")
    if expected_move_md:
        lines.append(f"_{expected_move_md.strip()}_")
        lines.append("")
    lines.append(flow_map_md.strip()
                 or "_No interpretable option-flow trades for today._")
    lines.append("")

    # ---- Plan ----
    lines.append("## Suggested swing levels")
    lines.append(f"- Bias to gravitate toward **${mp:,.0f}** (Max Pain) into expiry.")
    if cw:
        lines.append(f"- Resistance to fade: **${cw[0].strike:,.0f}** "
                     f"(largest call wall, OI {_fmt_int(cw[0].call_oi)}).")
    if pw:
        lines.append(f"- Support to buy: **${pw[0].strike:,.0f}** "
                     f"(largest put wall, OI {_fmt_int(pw[0].put_oi)}).")
    lines.append("")

    if notes:
        lines.append("## Notes")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append("---")
    lines.append("_Sources: CME Daily Settlements (futures) + QuikStrike Open "
                 "Interest Profile / Most Active Strikes / Globex Trade Browser._")
    return "\n".join(lines)
