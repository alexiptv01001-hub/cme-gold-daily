"""Unit tests for flow_map clustering and Markdown rendering."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flow_levels import (
    BEARISH_TARGET, BULLISH_TARGET, FlowLevel, RESISTANCE, SUPPORT,
)
from flow_map import bucket_for, cluster, render_flow_map


def _lvl(price: float, kind: str, weight: int = 100,
         time_ct: str = "10:00 AM") -> FlowLevel:
    return FlowLevel(
        price=price, kind=kind, strategy_kind="x",
        description=f"{kind}@{price}", weight=weight,
        expiry_code="OGM6", time_ct=time_ct, venue="BLOCK")


def test_bucket_for_kinds():
    assert bucket_for(_lvl(4800, RESISTANCE)) == "resistance"
    assert bucket_for(_lvl(4500, SUPPORT)) == "support"
    assert bucket_for(_lvl(4900, BULLISH_TARGET)) == "bullish_target"
    assert bucket_for(_lvl(4400, BEARISH_TARGET)) == "bearish_target"


def test_cluster_collapses_nearby_prices_into_one_bucket():
    lvls = [
        _lvl(4799, RESISTANCE, weight=100),
        _lvl(4801, RESISTANCE, weight=200),
        _lvl(4830, RESISTANCE, weight=150),
    ]
    clusters = cluster(lvls, window=5.0)
    res = [c for c in clusters if c.bucket == "resistance"]
    # 4799/4801 cluster + 4830 cluster
    assert len(res) == 2
    by_price = {round(c.price): c for c in res}
    assert 4800 in by_price
    assert by_price[4800].total_weight == 300
    assert 4830 in by_price


def test_cluster_keeps_buckets_separate():
    lvls = [
        _lvl(4700, RESISTANCE, weight=50),
        _lvl(4700, SUPPORT, weight=80),    # same price, different bucket
    ]
    clusters = cluster(lvls)
    buckets = [c.bucket for c in clusters]
    assert "resistance" in buckets and "support" in buckets


def test_render_flow_map_emits_required_subsections():
    lvls = [
        _lvl(4800, RESISTANCE, weight=500),
        _lvl(4500, SUPPORT, weight=300),
        _lvl(4900, BULLISH_TARGET, weight=200),
        _lvl(4400, BEARISH_TARGET, weight=100),
    ]
    md = render_flow_map(lvls, spot=4700.0)
    for needle in ("Resistance / range top", "Support / range bottom",
                   "Bullish targets", "Bearish targets",
                   "$4,800", "$4,500", "$4,900", "$4,400"):
        assert needle in md, f"missing {needle!r}"


def test_render_flow_map_handles_empty():
    md = render_flow_map([], spot=4700.0)
    assert "No flow-derived levels" in md
