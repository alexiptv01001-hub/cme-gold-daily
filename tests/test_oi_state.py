"""Unit tests for ΔOI state persistence."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_annotate_with_delta_against_stored_baseline(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("CME_OI_STATE", str(Path(tmp) / "oi.json"))
        # Reload module so it picks up the new env var.
        import importlib
        import oi_state
        importlib.reload(oi_state)
        from maxpain import StrikeRow

        baseline = [
            StrikeRow(4700, call_oi=100, put_oi=200),
            StrikeRow(4800, call_oi=150, put_oi=180),
        ]
        oi_state.store_oi("OG", "JUN26", "05/06/2026", baseline)

        today = [
            StrikeRow(4700, call_oi=120, put_oi=190),
            StrikeRow(4800, call_oi=145, put_oi=200),
        ]
        annotated = oi_state.annotate_with_delta("OG", "JUN26", today)
        deltas = {r.strike: (r.call_oi_change, r.put_oi_change) for r in annotated}
        assert deltas == {4700: (20, -10), 4800: (-5, 20)}


def test_annotate_with_delta_no_prior_returns_zero(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("CME_OI_STATE", str(Path(tmp) / "oi.json"))
        import importlib
        import oi_state
        importlib.reload(oi_state)
        from maxpain import StrikeRow

        today = [StrikeRow(4700, call_oi=120, put_oi=190)]
        annotated = oi_state.annotate_with_delta("OG", "JUN26", today)
        assert annotated[0].call_oi_change == 0
        assert annotated[0].put_oi_change == 0
