"""CME GC futures settlement fetcher (public API, no auth required)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from curl_cffi import requests as creq

GC_PRODUCT_ID = 437  # COMEX Gold Futures (GC)
SETTLE_URL_TMPL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/"
    "{pid}/FUT?tradeDate={mdy}"
)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class FutureSettle:
    month: str        # e.g. "JUN 26"
    open_: Optional[float]
    high: Optional[float]
    low: Optional[float]
    last: Optional[float]
    change: Optional[float]
    settle: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]


def _f(x: str | None) -> Optional[float]:
    if x in (None, "", "-"):
        return None
    s = str(x).replace(",", "").rstrip("AB").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _i(x: str | None) -> Optional[int]:
    f = _f(x)
    return int(f) if f is not None else None


def fetch_gc_settlements(date: datetime | None = None) -> tuple[str, list[FutureSettle]]:
    """Return (trade_date_str, list_of_settlements_sorted_by_month)."""
    if date is None:
        date = datetime.now(timezone.utc)
    mdy = date.strftime("%m/%d/%Y")
    url = SETTLE_URL_TMPL.format(pid=GC_PRODUCT_ID, mdy=mdy)
    r = creq.get(url, impersonate="chrome120",
                 headers={"User-Agent": UA, "Accept": "application/json"},
                 timeout=20)
    r.raise_for_status()
    data = r.json()
    rows = data.get("settlements", [])
    out = [
        FutureSettle(
            month=row.get("month", ""),
            open_=_f(row.get("open")),
            high=_f(row.get("high")),
            low=_f(row.get("low")),
            last=_f(row.get("last")),
            change=_f(row.get("change") or row.get("priorSettle")),
            settle=_f(row.get("settle")),
            volume=_i(row.get("volume")),
            open_interest=_i(row.get("openInterest")),
        )
        for row in rows
    ]
    return data.get("tradeDate", mdy), out


_MONTH_RE = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
             "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def is_real_month(label: str) -> bool:
    """True if label looks like 'JUN 26' (a real expiration month)."""
    if not label:
        return False
    parts = label.strip().upper().split()
    return len(parts) >= 2 and parts[0] in _MONTH_RE


def front_active(rows: list[FutureSettle]) -> FutureSettle | None:
    """Return the contract month with the largest open interest (most active)."""
    listed = [r for r in rows
              if r.open_interest is not None and is_real_month(r.month)]
    if not listed:
        return None
    return max(listed, key=lambda r: r.open_interest)


if __name__ == "__main__":
    # Try today, then yesterday (settlement publishes after market close).
    for delta in range(0, 5):
        d = datetime.now(timezone.utc) - timedelta(days=delta)
        try:
            td, rows = fetch_gc_settlements(d)
        except Exception as e:
            print(f"-{delta}d: {e}")
            continue
        if rows:
            print(f"Trade date: {td}  ({d.date()})  rows={len(rows)}")
            front = front_active(rows)
            print(f"  Front (max OI): {front}")
            print("  All months:")
            for r in rows[:10]:
                print(f"    {r.month:>8}  settle={r.settle}  vol={r.volume}  OI={r.open_interest}")
            break
