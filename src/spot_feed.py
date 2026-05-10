"""Intraday GC futures spot feed via Yahoo Finance.

Yahoo's `GC=F` symbol tracks the front-month COMEX gold futures
continuous contract.  The 1-minute history is delayed ~15 minutes for
free users — fine for our purpose (we only need it to label block
trades from earlier in the day with the futures price at that moment).

We use ``yfinance`` because it has no API key and handles its own
session / cookies.  If ``yfinance`` is missing or the network is
blocked, the loader returns ``None`` and the daily report falls back
to settlement price (good enough for swing analysis).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class IntradayBars:
    """Minimal OHLC table — keyed by UTC datetime, ascending."""
    times_utc: list[datetime]      # one timestamp per bar (UTC)
    closes: list[float]            # close price per bar


def fetch_gc_intraday(days: int = 2) -> Optional[IntradayBars]:
    """Fetch the last ``days`` of GC=F 1-minute bars.

    Returns ``None`` if the Yahoo client is unavailable or returns
    nothing — caller should treat this as "no intraday spot, use
    settlement instead".
    """
    try:
        import yfinance as yf  # noqa: WPS433 — optional dep
    except ImportError:
        return None

    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=max(1, days))
    try:
        df = yf.Ticker("GC=F").history(
            start=start, end=end, interval="1m", prepost=True)
    except Exception:  # noqa: BLE001 — Yahoo throws lots of generic errors
        return None
    if df is None or df.empty:
        return None

    # Ensure tz-aware UTC index.
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")

    times: list[datetime] = [t.to_pydatetime() for t in idx]
    closes: list[float] = [float(x) for x in df["Close"].tolist()]
    return IntradayBars(times_utc=times, closes=closes)


def spot_at(bars: IntradayBars | None, t: datetime) -> Optional[float]:
    """Return the close of the latest bar at-or-before ``t``.

    ``t`` must be tz-aware UTC.  Returns ``None`` if ``bars`` is empty
    or every bar is in the future relative to ``t``.
    """
    if bars is None or not bars.times_utc:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    # Linear scan — bars list is small (< 5 days × 24h × 60m = 7,200
    # entries), and we're only called a few times per day.
    last: Optional[float] = None
    for ts, close in zip(bars.times_utc, bars.closes):
        if ts <= t:
            last = close
        else:
            break
    return last


_CT_OFFSET = timedelta(hours=-5)  # CT is UTC-5 in summer; CME timestamps in
                                   # the block-data feed are CDT during DST.


def parse_block_time_to_utc(time_ct: str,
                            trade_date: datetime | None = None) -> Optional[datetime]:
    """Convert a block-trade CT timestamp like '11:29:29 AM' to UTC.

    The block-data feed only publishes the time-of-day; the date comes
    from the page header (today's date in CT).  We approximate by using
    the caller-supplied ``trade_date`` (default = today UTC).

    Returns ``None`` on parse failure.
    """
    if trade_date is None:
        trade_date = datetime.now(timezone.utc)
    # Strip trailing tz/whitespace
    s = (time_ct or "").strip().upper()
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
        except ValueError:
            continue
        # Combine with trade_date in CT, then shift to UTC.
        ct_dt = datetime(
            trade_date.year, trade_date.month, trade_date.day,
            t.hour, t.minute, t.second,
        )
        return (ct_dt - _CT_OFFSET).replace(tzinfo=timezone.utc)
    return None
