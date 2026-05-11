"""Main entry — generate the daily gold-options swing-trading report.

Run flow:
    1. Log into CME via Selenium (cookies persisted in /home/ubuntu/.cme).
    2. Fetch GC futures settlement and OG monthly option chain via the
       authenticated browser fetch().
    3. Annotate strike rows with ΔOI vs the prior trading day.
    4. Render the report as Markdown to stdout.
    5. Persist today's OI as tomorrow's baseline.

If anything fails (login, captcha, missing data) we fall back to a
"futures-only" report that explains what is missing, so the user still
gets something useful and is informed.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone

from block_trades import fetch_gold_blocks, render_blocks_md
from cme_login import ensure_logged_in, make_driver
from electronic_trades import fetch_gold_electronic_trades
from flow_levels import FlowLevel, levels_for
from flow_map import render_expected_move, render_flow_map
from maxpain import StrikeRow
from oi_state import annotate_with_delta, store_oi
from options_api import (
    chain_volume_summary, fetch_gc_futures_settle, fetch_option_chain,
    fetch_option_expirations, front_active_future, front_monthly_expiration,
    most_active_by_volume, FutureSettle,
)
from report import render_report
from spot_feed import fetch_gc_intraday, parse_block_time_to_utc, spot_at
from strategy import classify
from trades import TradeRecord, from_block_trade


def _futures_only(td: str, front: FutureSettle, notes: list[str]) -> str:
    def _money(x):
        return f"${x:,.1f}" if x is not None else "—"
    def _signed(x):
        return f"({'+' if x>=0 else ''}{x:,.1f})" if x is not None else ""
    lines = [
        "# Золото (GC) — ежедневные уровни (только фьючерсы)",
        f"_Торговая сессия: **{td}** • отчёт сгенерирован "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Цена (фронт-месяц GC)",
        f"- Контракт: **{front.month}**",
        f"- Расчётная цена: **{_money(front.settle)}** "
        f"(последняя {_money(front.last)}, изменение {_signed(front.change)})",
        f"- Объём: {front.volume:,}  •  OI: {front.open_interest:,}"
        if front.volume and front.open_interest else "—",
        "",
    ]
    if notes:
        lines.append("## Заметки")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    lines.append("---")
    lines.append("_Источник: CME Daily Settlements (фьючерсы)._")
    return "\n".join(lines)


def main() -> str:
    notes: list[str] = []
    drv = make_driver()
    try:
        ensure_logged_in(drv)

        # 1) Futures settlement (front-month, used as price reference).
        td_f, fut_rows = fetch_gc_futures_settle(drv)
        front = front_active_future(fut_rows)
        if front is None:
            raise RuntimeError("could not identify front-month gold contract")

        # 2) Monthly OG expirations + pick the front monthly.
        exps = fetch_option_expirations(drv)
        front_exp = front_monthly_expiration(exps)
        if front_exp is None:
            notes.append("_Не найдены будущие месячные экспирации OG — "
                         "данные по опционам пропущены._")
            return _futures_only(td_f, front, notes)

        # 3) Strike-level OI for the front-month chain.
        try:
            td_o, raw_rows = fetch_option_chain(drv, front_exp)
        except Exception as e:  # noqa: BLE001
            notes.append(f"_Не удалось получить цепочку опционов: "
                         f"{type(e).__name__}: {e}._")
            return _futures_only(td_f, front, notes)

        # 4) Volume / most-active for the same chain.
        try:
            vol_rows = chain_volume_summary(drv, front_exp)
            most_active = [(k, t[0].upper(), v) for k, t, v
                           in most_active_by_volume(vol_rows, n=5)]
        except Exception as e:  # noqa: BLE001
            most_active = []
            notes.append(f"_Сводка по объёмам недоступна: {e}._")

        # 5) Globex Trade Browser — public block-trades feed.  Filtered to
        #    gold (GC futures + OG monthly/weekly options).
        try:
            gold_blocks = fetch_gold_blocks(drv)
            blocks_md = render_blocks_md(gold_blocks, top_n=8)
        except Exception as e:  # noqa: BLE001
            gold_blocks = []
            blocks_md = ""
            notes.append(
                f"_Сбор блок-сделок не удался: {type(e).__name__}: {e}._")

        # 6) Electronic option trades (QuikStrike Globex Trade Browser).
        #    Returns [] today — see ``electronic_trades.py`` for status.
        try:
            elec_trades = fetch_gold_electronic_trades(drv)
        except Exception as e:  # noqa: BLE001
            elec_trades = []
            notes.append(
                f"_Сбор электронных сделок не удался: "
                f"{type(e).__name__}: {e}._")

    except KeyError as e:
        traceback.print_exc(file=sys.stderr)
        try:
            drv.quit()
        except Exception:
            pass
        return ("# Золото (GC) — ежедневный отчёт\n\n"
                f"_Не удалось запустить: не задана переменная окружения {e}. "
                "Установите CME_USERNAME и CME_PASSWORD как Devin-secrets._")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        try:
            drv.quit()
        except Exception:
            pass
        return ("# Золото (GC) — ежедневный отчёт\n\n"
                f"_Запуск завершился с ошибкой: {type(e).__name__}: {e}._")
    else:
        try:
            drv.quit()
        except Exception:
            pass

    # Annotate ΔOI vs persisted prior day, then update store.
    expiry_label = f"OG {front_exp.label} (monthly)"
    rows: list[StrikeRow] = annotate_with_delta("OG", expiry_label, raw_rows)
    store_oi("OG", expiry_label, td_o, raw_rows)

    # Flow-Levels-Map: classify each trade and derive premium-based price
    # levels.  We currently only use block trades; electronic trades from
    # the QuikStrike GTB are wired but disabled (see electronic_trades.py).
    flow_md, expected_md = _build_flow_map(
        gold_blocks, elec_trades, td=td_f, notes=notes,
    )

    return render_report(
        trade_date=td_f,
        front=_to_report_future(front),
        expiry_label=expiry_label,
        rows=rows,
        blocks_md=blocks_md,
        most_active=most_active,
        flow_map_md=flow_md,
        expected_move_md=expected_md,
        notes=notes,
    )


def _build_flow_map(
    gold_blocks,
    elec_trades: list[TradeRecord],
    *,
    td: str,
    notes: list[str],
) -> tuple[str, str]:
    """Classify each option trade and emit the Flow Levels Map markdown.

    Returns ``(flow_map_md, expected_move_md)``.  Both are empty strings
    if there is nothing to render.
    """
    # Pull intraday GC bars once so each block timestamp can be paired
    # with a recent spot price for the buy/sell heuristic and bullish/
    # bearish-target labelling.  This is best-effort — Yahoo can fail.
    try:
        bars = fetch_gc_intraday(days=2)
    except Exception as e:  # noqa: BLE001
        bars = None
        notes.append(
            f"_Внутридневной спот-фид по GC недоступен: "
            f"{type(e).__name__}: {e}._")

    # Convert block trades to the unified TradeRecord model.
    try:
        trade_dt = datetime.strptime(td, "%m/%d/%Y")
    except Exception:  # noqa: BLE001
        trade_dt = None
    block_records: list[TradeRecord] = []
    for b in gold_blocks or []:
        rec = from_block_trade(b)
        if trade_dt is not None:
            rec.time_utc = parse_block_time_to_utc(rec.time_ct, trade_dt)
        if rec.time_utc is not None and bars is not None:
            rec.spot_at_trade = spot_at(bars, rec.time_utc)
        block_records.append(rec)

    all_records: list[TradeRecord] = block_records + list(elec_trades)

    # Classify + price each leg-set.
    levels: list[FlowLevel] = []
    for rec in all_records:
        if not rec.option_legs:
            continue
        strat = classify(rec)
        levels.extend(levels_for(rec, strat))

    if not levels:
        return "", ""

    spot_now = bars.closes[-1] if bars and bars.closes else None
    flow_md = render_flow_map(levels, spot=spot_now, top_n=5)
    expected_md = render_expected_move(levels)
    return flow_md, expected_md


def _to_report_future(f: FutureSettle):
    """Adapter — report.py imports FutureSettle from futures.py, so re-create
    the row using that module's class so isinstance checks pass."""
    from futures import FutureSettle as RFS
    return RFS(
        month=f.month, open_=f.open_, high=f.high, low=f.low, last=f.last,
        change=f.change, settle=f.settle, volume=f.volume,
        open_interest=f.open_interest,
    )


if __name__ == "__main__":
    print(main())
