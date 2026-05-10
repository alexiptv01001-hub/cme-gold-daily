"""Unit tests for the unified trade data model + adapter."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from block_trades import BlockTrade, BlockTradeLeg
from trades import (
    FuturesLeg,
    OptionLeg,
    TradeRecord,
    _underlying_for,
    from_block_trade,
)


def test_underlying_for_monthly_and_weekly():
    assert _underlying_for("OGM6") == "GCM6"
    assert _underlying_for("OGM26") == "GCM26"
    # Weekly options 1OG/2OG/.../5OG → underlying = next monthly GC
    assert _underlying_for("1OGM6") == "GCM6"
    assert _underlying_for("3OGN6") == "GCN6"
    # Already a futures code → leave as is
    assert _underlying_for("GCM6") == "GCM6"


def test_from_block_trade_outright_call():
    bt = BlockTrade(
        time_ct="10:45:23 AM", trade_type="Option",
        legs=[BlockTradeLeg(
            product="Gold Option", sym="OGV6", qty=75,
            cp_strike="P4200.00", side="Buy", price=74.3,
        )])
    rec = from_block_trade(bt)
    assert rec.venue == "BLOCK"
    assert rec.time_ct == "10:45:23 AM"
    assert len(rec.option_legs) == 1
    assert len(rec.futures_legs) == 0
    leg = rec.option_legs[0]
    assert leg.expiry_code == "OGV6"
    assert leg.underlying_code == "GCV6"
    assert leg.is_call is False
    assert leg.strike == 4200.0
    assert leg.side == "Buy"
    assert leg.qty == 75
    assert leg.price == 74.3


def test_from_block_trade_spread_with_futures_hedge():
    bt = BlockTrade(
        time_ct="07:02:03 AM", trade_type="Spread",
        net_price=None, spread_qty=90,
        legs=[
            BlockTradeLeg(product="Gold Option", sym="OGM6", qty=90,
                          cp_strike="P4700.00", side="Buy", price=12.5),
            BlockTradeLeg(product="Gold Future", sym="GCM6", qty=41,
                          cp_strike="", side="Buy", price=4720.0),
            BlockTradeLeg(product="Gold Option", sym="OGU6", qty=60,
                          cp_strike="C5000.00", side="Sell", price=8.0),
            BlockTradeLeg(product="Gold Future", sym="GCV6", qty=23,
                          cp_strike="", side="Buy", price=4730.0),
        ])
    rec = from_block_trade(bt)
    # 2 option legs + 2 futures legs.
    assert len(rec.option_legs) == 2
    assert len(rec.futures_legs) == 2
    assert {l.expiry_code for l in rec.option_legs} == {"OGM6", "OGU6"}
    assert {l.contract_code for l in rec.futures_legs} == {"GCM6", "GCV6"}
    assert rec.spread_qty == 90
    # primary_expiry = most common (here both appear once → Counter picks
    # the first; either is fine, we just check it's one of them).
    assert rec.primary_expiry in ("OGM6", "OGU6")


def test_trade_record_gross_premium_and_total_qty():
    bt = BlockTrade(
        time_ct="11:00 AM", trade_type="Spread", spread_qty=10,
        legs=[
            BlockTradeLeg("Gold Option", "OGM6", qty=10, cp_strike="C4800.00",
                          side="Buy", price=20.0),
            BlockTradeLeg("Gold Option", "OGM6", qty=10, cp_strike="C4900.00",
                          side="Sell", price=12.0),
        ])
    rec = from_block_trade(bt)
    assert rec.total_option_qty == 20
    # 10*20 + 10*12 = 320
    assert rec.gross_premium == 320.0
