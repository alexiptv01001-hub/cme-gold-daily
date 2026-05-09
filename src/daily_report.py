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
from maxpain import StrikeRow
from oi_state import annotate_with_delta, store_oi
from options_api import (
    chain_volume_summary, fetch_gc_futures_settle, fetch_option_chain,
    fetch_option_expirations, front_active_future, front_monthly_expiration,
    most_active_by_volume, FutureSettle,
)
from report import render_report


def _futures_only(td: str, front: FutureSettle, notes: list[str]) -> str:
    def _money(x):
        return f"${x:,.1f}" if x is not None else "—"
    def _signed(x):
        return f"({'+' if x>=0 else ''}{x:,.1f})" if x is not None else ""
    lines = [
        "# Gold (GC) — Daily Levels (futures-only)",
        f"_Trade date: **{td}** • generated "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Price (front-month GC)",
        f"- Contract: **{front.month}**",
        f"- Settlement: **{_money(front.settle)}** "
        f"(last {_money(front.last)}, change {_signed(front.change)})",
        f"- Volume: {front.volume:,}  •  OI: {front.open_interest:,}"
        if front.volume and front.open_interest else "—",
        "",
    ]
    if notes:
        lines.append("## Notes")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    lines.append("---")
    lines.append("_Source: CME Daily Settlements (futures)._")
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
            notes.append("_No future monthly OG expirations found — "
                         "skipping options data._")
            return _futures_only(td_f, front, notes)

        # 3) Strike-level OI for the front-month chain.
        try:
            td_o, raw_rows = fetch_option_chain(drv, front_exp)
        except Exception as e:  # noqa: BLE001
            notes.append(f"_Option-chain fetch failed: {type(e).__name__}: {e}._")
            return _futures_only(td_f, front, notes)

        # 4) Volume / most-active for the same chain.
        try:
            vol_rows = chain_volume_summary(drv, front_exp)
            most_active = [(k, t[0].upper(), v) for k, t, v
                           in most_active_by_volume(vol_rows, n=5)]
        except Exception as e:  # noqa: BLE001
            most_active = []
            notes.append(f"_Volume summary unavailable: {e}._")

        # 5) Globex Trade Browser — public block-trades feed.  Filtered to
        #    gold (GC futures + OG monthly/weekly options).
        try:
            gold_blocks = fetch_gold_blocks(drv)
            blocks_md = render_blocks_md(gold_blocks, top_n=8)
        except Exception as e:  # noqa: BLE001
            blocks_md = ""
            notes.append(
                f"_Block-trade scrape failed: {type(e).__name__}: {e}._")

    except KeyError as e:
        traceback.print_exc(file=sys.stderr)
        try:
            drv.quit()
        except Exception:
            pass
        return ("# Gold (GC) — Daily Report\n\n"
                f"_Cannot run: missing env var {e}.  Set CME_USERNAME and "
                "CME_PASSWORD as Devin secrets._")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        try:
            drv.quit()
        except Exception:
            pass
        return ("# Gold (GC) — Daily Report\n\n"
                f"_Run failed: {type(e).__name__}: {e}._")
    else:
        try:
            drv.quit()
        except Exception:
            pass

    # Annotate ΔOI vs persisted prior day, then update store.
    expiry_label = f"OG {front_exp.label} (monthly)"
    rows: list[StrikeRow] = annotate_with_delta("OG", expiry_label, raw_rows)
    store_oi("OG", expiry_label, td_o, raw_rows)

    return render_report(
        trade_date=td_f,
        front=_to_report_future(front),
        expiry_label=expiry_label,
        rows=rows,
        blocks_md=blocks_md,
        most_active=most_active,
        notes=notes,
    )


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
