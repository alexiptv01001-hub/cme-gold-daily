"""Persist previous-day strike-level open interest so we can compute ΔOI.

Stored as JSON in /home/ubuntu/.cme/oi_history.json (or $CME_OI_STATE).
Keyed by (trade_date, product_code, expiry_label) -> {strike: (call_oi, put_oi)}.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from maxpain import StrikeRow

STATE_FILE = Path(os.environ.get("CME_OI_STATE", "/home/ubuntu/.cme/oi_history.json"))


def _load() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save(d: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(d, indent=2))


def _key(product: str, expiry: str) -> str:
    return f"{product}|{expiry}"


def previous_oi(product: str, expiry: str) -> Optional[dict[float, tuple[int, int]]]:
    """Return prior strike OI map, or None if none stored."""
    state = _load()
    bucket = state.get(_key(product, expiry))
    if not bucket or "rows" not in bucket:
        return None
    return {float(k): tuple(v) for k, v in bucket["rows"].items()}


def store_oi(product: str, expiry: str, trade_date: str,
             rows: list[StrikeRow]) -> None:
    """Persist today's strike OI as the new baseline for tomorrow."""
    state = _load()
    state[_key(product, expiry)] = {
        "trade_date": trade_date,
        "rows": {f"{r.strike}": [r.call_oi, r.put_oi] for r in rows},
    }
    _save(state)


def annotate_with_delta(product: str, expiry: str,
                        rows: list[StrikeRow]) -> list[StrikeRow]:
    """Return new StrikeRow list with ΔOI fields filled in (vs stored prior)."""
    prior = previous_oi(product, expiry) or {}
    out: list[StrikeRow] = []
    for r in rows:
        pc, pp = prior.get(r.strike, (r.call_oi, r.put_oi))
        out.append(StrikeRow(
            strike=r.strike,
            call_oi=r.call_oi, put_oi=r.put_oi,
            call_oi_change=r.call_oi - pc,
            put_oi_change=r.put_oi  - pp,
        ))
    return out
