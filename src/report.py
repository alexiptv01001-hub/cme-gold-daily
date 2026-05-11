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
    lines.append(f"# Золото (GC) — ежедневные уровни для свинг-трейдинга")
    lines.append(f"_Торговая сессия: **{trade_date}** • отчёт сгенерирован "
                 f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")

    # ---- Цена фронт-месяца ----
    lines.append("## Цена (фронт-месяц GC)")
    lines.append(f"- Контракт: **{front.month}**")
    lines.append(f"- Расчётная цена: **{_fmt_money(front.settle)}**  "
                 f"(последняя {_fmt_money(front.last)}, изменение {_signed(front.change)})")
    lines.append(f"- Объём: {_fmt_int(front.volume)}  •  "
                 f"OI: {_fmt_int(front.open_interest)}")
    lines.append("")

    # ---- Max Pain ----
    lines.append(f"## Max Pain (точка максимальной боли) — {expiry_label}")
    lines.append(f"- **Страйк Max Pain:** ${mp:,.0f}")
    if px is not None:
        delta = mp - px
        bias = ("рынок будет **сползать вниз** к Max Pain"
                if delta < -1 else "рынок будет **подниматься вверх** к Max Pain"
                if delta > 1 else "цена прямо на Max Pain")
        lines.append(f"- Расстояние от цены: {delta:+,.0f} п. ({bias})")
    lines.append("")

    # ---- Стены коллов (сопротивление) ----
    lines.append("## Сопротивление — стены коллов (топ-3 по OI)")
    lines.append("| Страйк | OI коллов | ΔOI |")
    lines.append("|---:|---:|---:|")
    for r in cw:
        lines.append(f"| ${r.strike:,.0f} | {_fmt_int(r.call_oi)} "
                     f"| {_signed(r.call_oi_change)} |")
    lines.append("")

    # ---- Стены путов (поддержка) ----
    lines.append("## Поддержка — стены путов (топ-3 по OI)")
    lines.append("| Страйк | OI путов | ΔOI |")
    lines.append("|---:|---:|---:|")
    for r in pw:
        lines.append(f"| ${r.strike:,.0f} | {_fmt_int(r.put_oi)} "
                     f"| {_signed(r.put_oi_change)} |")
    lines.append("")

    # ---- Самые активные страйки ----
    if most_active:
        lines.append("## Самые активные страйки (по объёму за вчера)")
        lines.append("| Страйк | Тип | Объём |")
        lines.append("|---:|:---:|---:|")
        for k, side, vol in most_active[:5]:
            lines.append(f"| ${k:,.0f} | {side} | {_fmt_int(vol)} |")
        lines.append("")

    # ---- Блок-сделки (институциональный поток из Globex Trade Browser) ----
    lines.append("## Институциональный поток \u2014 Globex Trade Browser (крупнейшие блок-сделки)")
    lines.append(blocks_md.strip()
                 or "_Сегодня крупных блок-сделок по золоту не зафиксировано._")
    lines.append("")

    # ---- Карта уровней флоу (математика премии) ----
    lines.append("## Карта уровней флоу (выведено из опционного потока)")
    if expected_move_md:
        lines.append(f"_{expected_move_md.strip()}_")
        lines.append("")
    lines.append(flow_map_md.strip()
                 or "_Сегодня нет интерпретируемых опционных сделок для построения карты._")
    lines.append("")

    # ---- План ----
    lines.append("## Предлагаемые уровни для свинг-трейдинга")
    lines.append(f"- Цена будет тяготеть к **${mp:,.0f}** (Max Pain) к экспирации.")
    if cw:
        lines.append(f"- Сопротивление для шорта: **${cw[0].strike:,.0f}** "
                     f"(крупнейшая стена коллов, OI {_fmt_int(cw[0].call_oi)}).")
    if pw:
        lines.append(f"- Поддержка для покупки: **${pw[0].strike:,.0f}** "
                     f"(крупнейшая стена путов, OI {_fmt_int(pw[0].put_oi)}).")
    lines.append("")

    if notes:
        lines.append("## Заметки")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append("---")
    lines.append("_Источники: CME Daily Settlements (фьючерсы) + QuikStrike Open "
                 "Interest Profile / Most Active Strikes / Globex Trade Browser._")
    return "\n".join(lines)
