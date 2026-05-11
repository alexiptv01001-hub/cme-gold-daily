"""Unit tests for the Markdown report formatter."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from futures import FutureSettle
from maxpain import StrikeRow
from report import render_report


def test_render_report_contains_required_sections():
    front = FutureSettle(
        month="JUN 26", open_=4700.0, high=4720.0, low=4690.0, last=4710.0,
        change=10.0, settle=4710.0, volume=100000, open_interest=200000,
    )
    rows = [
        StrikeRow(4500, call_oi=100, put_oi=10, call_oi_change=5,  put_oi_change=-3),
        StrikeRow(4600, call_oi=80,  put_oi=20, call_oi_change=2,  put_oi_change=1),
        StrikeRow(4700, call_oi=50,  put_oi=50, call_oi_change=0,  put_oi_change=0),
        StrikeRow(4800, call_oi=20,  put_oi=80, call_oi_change=-1, put_oi_change=4),
        StrikeRow(4900, call_oi=10,  put_oi=100,call_oi_change=-3, put_oi_change=8),
    ]
    blocks_md = "- **Spread** (10:00 AM CT): Buy 100 OGM6 P4700 @ 12.5"
    most = [(4700.0, "C", 3000)]
    md = render_report(
        trade_date="05/07/2026", front=front,
        expiry_label="OG JUN 26 (monthly)", rows=rows,
        blocks_md=blocks_md, most_active=most,
    )
    for needle in ("# Золото (GC)", "Max Pain",
                   "стены коллов", "стены путов",
                   "Самые активные", "Globex Trade Browser",
                   "свинг-трейдинга", "$4,710.0", "$4,700",
                   "OGM6 P4700"):
        assert needle in md, f"missing section/value: {needle!r}"


def test_render_report_handles_empty_blocks():
    front = FutureSettle(
        month="JUN 26", open_=4700.0, high=4720.0, low=4690.0, last=4710.0,
        change=10.0, settle=4710.0, volume=100000, open_interest=200000,
    )
    rows = [
        StrikeRow(4500, call_oi=100, put_oi=10),
        StrikeRow(4600, call_oi=80, put_oi=20),
        StrikeRow(4700, call_oi=50, put_oi=50),
        StrikeRow(4800, call_oi=20, put_oi=80),
        StrikeRow(4900, call_oi=10, put_oi=100),
    ]
    md = render_report(
        trade_date="05/07/2026", front=front,
        expiry_label="OG JUN 26", rows=rows,
        blocks_md="", most_active=[],
    )
    assert "крупных блок-сделок по золоту не зафиксировано" in md
