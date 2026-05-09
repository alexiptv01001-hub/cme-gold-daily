"""Unit tests for the Max Pain math module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from maxpain import (StrikeRow, biggest_call_oi_changes,
                     biggest_put_oi_changes, call_walls, max_pain, put_walls)


def _rows() -> list[StrikeRow]:
    return [
        StrikeRow(4500, call_oi=100, put_oi=10),
        StrikeRow(4600, call_oi=80,  put_oi=20),
        StrikeRow(4700, call_oi=50,  put_oi=50),
        StrikeRow(4800, call_oi=20,  put_oi=80),
        StrikeRow(4900, call_oi=10,  put_oi=100),
    ]


def test_max_pain_balanced_chain():
    mp, pain = max_pain(_rows())
    # Balanced symmetric distribution -> central strike is the min.
    assert mp == 4700
    assert pain[4700] == min(pain.values())


def test_max_pain_call_heavy():
    rows = [
        StrikeRow(4500, call_oi=1000, put_oi=10),
        StrikeRow(4600, call_oi=500,  put_oi=10),
        StrikeRow(4700, call_oi=10,   put_oi=10),
    ]
    # Heavy call OI at low strikes pushes pain min toward the lowest strike.
    mp, _ = max_pain(rows)
    assert mp == 4500


def test_max_pain_put_heavy():
    rows = [
        StrikeRow(4700, call_oi=10, put_oi=10),
        StrikeRow(4800, call_oi=10, put_oi=500),
        StrikeRow(4900, call_oi=10, put_oi=1000),
    ]
    mp, _ = max_pain(rows)
    assert mp == 4900


def test_max_pain_empty():
    with pytest.raises(ValueError):
        max_pain([])


def test_call_walls_orders_by_call_oi():
    walls = call_walls(_rows(), n=3)
    assert [w.strike for w in walls] == [4500, 4600, 4700]


def test_put_walls_orders_by_put_oi():
    walls = put_walls(_rows(), n=3)
    assert [w.strike for w in walls] == [4900, 4800, 4700]


def test_biggest_oi_changes_uses_absolute_value():
    rows = [
        StrikeRow(4500, 0, 0, call_oi_change=+50, put_oi_change=-100),
        StrikeRow(4600, 0, 0, call_oi_change=-200, put_oi_change=+30),
        StrikeRow(4700, 0, 0, call_oi_change=+80, put_oi_change=+150),
    ]
    big_c = biggest_call_oi_changes(rows, n=2)
    assert [r.strike for r in big_c] == [4600, 4700]
    big_p = biggest_put_oi_changes(rows, n=2)
    assert [r.strike for r in big_p] == [4700, 4500]
