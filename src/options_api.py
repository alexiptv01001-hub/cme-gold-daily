"""CME options + futures fetcher via authenticated browser fetch().

CME's public REST endpoints reject direct scrapers from data-center IPs
("This IP address is blocked due to suspected web scraping activity").  The
same endpoints work fine when called from a browser tab on cmegroup.com that
is logged into a free CME account, so we run the requests *through* the
authenticated Selenium driver using fetch().

Endpoints used:

  /CmeWS/mvc/Settlements/Futures/Settlements/{pid}/FUT?
      strategy=DEFAULT & tradeDate=MM/DD/YYYY & pageSize=500 & isProtected
        -> futures settlement chain for product 437 (GC)

  /CmeWS/mvc/Settlements/Options/Settlements/{pid}/OOF?
      monthYear=OG{M}{YY} & strategy=DEFAULT & tradeDate=MM/DD/YYYY & isProtected
        -> options settlement chain for product 192 (Gold OG monthly).
           monthYear uses CME futures month codes:
             F=Jan G=Feb H=Mar J=Apr K=May M=Jun
             N=Jul Q=Aug U=Sep V=Oct X=Nov Z=Dec
           Each row contains: strike, type ("Call"/"Put"), settle, volume,
           openInterest.

The Options OOF response covers ALL strikes for the requested expiration —
not just ATM — which is what we need for Max Pain.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By

from maxpain import StrikeRow

GC_FUTURES_PRODUCT_ID = 437
OG_OPTIONS_PRODUCT_ID = 192  # Gold "American Options" — the standard monthly

MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
              7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}

OPTIONS_PAGE = "https://www.cmegroup.com/markets/metals/precious/gold.quotes.options.html"


# ----------------------------------------------------------------------------
# Settlement row dataclasses
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class FutureSettle:
    month: str
    open_: Optional[float]
    high: Optional[float]
    low: Optional[float]
    last: Optional[float]
    change: Optional[float]
    settle: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]


@dataclass(frozen=True)
class OptionExpiration:
    label: str             # e.g. "Jun 2026"
    product_id: int        # 192 for monthly OG
    year: int
    month: int             # 1..12
    last_trade_date: str   # ISO yyyy-mm-dd
    underlying_future: str # e.g. "GCM6"

    @property
    def cme_code(self) -> str:
        """CME options code with month/year, e.g. 'OGM26' for Jun 2026."""
        return f"OG{MONTH_CODE[self.month]}{self.year % 100:02d}"


# ----------------------------------------------------------------------------
# Browser fetch helper
# ----------------------------------------------------------------------------


_FETCH_JS = """
const cb = arguments[arguments.length - 1];
const url = arguments[0];
(async () => {
  try {
    const r = await fetch(url, {
      credentials: 'include',
      headers: {'Accept':'application/json'},
    });
    const text = await r.text();
    cb(JSON.stringify({status: r.status, body: text}));
  } catch (e) {
    cb(JSON.stringify({status: 0, body: 'fetch error: ' + e.toString()}));
  }
})();
"""


def _ensure_on_origin(driver: webdriver.Chrome) -> None:
    """Make sure the driver is on a cmegroup.com page so fetch() is same-origin."""
    cur = (driver.current_url or "").lower()
    if "cmegroup.com" in cur and "login.cmegroup.com" not in cur:
        return
    driver.get(OPTIONS_PAGE)
    time.sleep(5)
    # Accept cookie banner if present (otherwise some XHRs are gated).
    try:
        btn = driver.find_element(By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(1)
    except Exception:
        pass


def _fetch_json(driver: webdriver.Chrome, path: str) -> tuple[int, object]:
    """Run fetch() inside the page and return (status, parsed_body_or_text)."""
    _ensure_on_origin(driver)
    driver.set_script_timeout(60)
    sep = "&" if "?" in path else "?"
    full = f"{path}{sep}_t={int(time.time()*1000)}"
    raw = driver.execute_async_script(_FETCH_JS, full)
    payload = json.loads(raw)
    body_text = payload.get("body", "")
    try:
        return int(payload["status"]), json.loads(body_text)
    except json.JSONDecodeError:
        return int(payload["status"]), body_text


# ----------------------------------------------------------------------------
# Public fetchers
# ----------------------------------------------------------------------------


def _f(x) -> Optional[float]:
    if x in (None, "", "-"):
        return None
    s = str(x).replace(",", "").rstrip("AB").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _i(x) -> Optional[int]:
    f = _f(x)
    return int(f) if f is not None else None


_MONTHS_3 = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
             "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def is_real_month(label: str) -> bool:
    if not label:
        return False
    parts = label.strip().upper().split()
    return len(parts) >= 2 and parts[0] in _MONTHS_3


def fetch_gc_futures_settle(
    driver: webdriver.Chrome,
    target: datetime | None = None,
) -> tuple[str, list[FutureSettle]]:
    """Return (trade_date_str, list_of_settlements).

    Walks back up to 6 days from `target` (default now-UTC) until non-empty.
    """
    if target is None:
        target = datetime.now(timezone.utc)
    last_err: Exception | None = None
    for delta in range(0, 6):
        d = target - timedelta(days=delta)
        mdy = d.strftime("%m/%d/%Y")
        path = (f"/CmeWS/mvc/Settlements/Futures/Settlements/"
                f"{GC_FUTURES_PRODUCT_ID}/FUT?strategy=DEFAULT&tradeDate={mdy}"
                f"&pageSize=500&isProtected")
        try:
            status, body = _fetch_json(driver, path)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if status != 200 or not isinstance(body, dict):
            continue
        rows_raw = body.get("settlements") or []
        if not rows_raw:
            continue
        rows = [
            FutureSettle(
                month=r.get("month", ""),
                open_=_f(r.get("open")),
                high=_f(r.get("high")),
                low=_f(r.get("low")),
                last=_f(r.get("last")),
                change=_f(r.get("change")),
                settle=_f(r.get("settle")),
                volume=_i(r.get("volume")),
                open_interest=_i(r.get("openInterest")),
            )
            for r in rows_raw
        ]
        return body.get("tradeDate", mdy), rows
    if last_err:
        raise last_err
    raise RuntimeError("no GC futures settlement found in past 6 days")


def front_active_future(rows: list[FutureSettle]) -> FutureSettle | None:
    listed = [r for r in rows
              if r.open_interest is not None and is_real_month(r.month)]
    if not listed:
        return None
    return max(listed, key=lambda r: r.open_interest)


def fetch_option_expirations(driver: webdriver.Chrome) -> list[OptionExpiration]:
    """Return the list of monthly OG expirations (product 192)."""
    path = (f"/CmeWS/mvc/atm/expirations/{GC_FUTURES_PRODUCT_ID}?isProtected")
    status, body = _fetch_json(driver, path)
    if status != 200 or not isinstance(body, list):
        raise RuntimeError(f"expirations endpoint failed: {status} {str(body)[:200]}")
    out: list[OptionExpiration] = []
    for group in body:
        if not isinstance(group, dict):
            continue
        if group.get("productId") != OG_OPTIONS_PRODUCT_ID:
            continue
        for e in group.get("contractExpirations") or []:
            # `expirationMonth` is 0-indexed from the page layer; verify against label.
            label = e.get("label", "")
            year = int(e.get("expirationYear"))
            # Prefer to derive month from `displayExpirationMonth` ('06' -> 6)
            disp = (e.get("displayExpirationMonth") or "").lstrip("0")
            month = int(disp) if disp.isdigit() else int(e.get("expirationMonth") or 0) + 1
            out.append(OptionExpiration(
                label=label, product_id=OG_OPTIONS_PRODUCT_ID,
                year=year, month=month,
                last_trade_date=str(e.get("lastTradeDate", ""))[:10],
                underlying_future=str(e.get("underlyingFutureContract", "")),
            ))
    return out


def front_monthly_expiration(
    expirations: list[OptionExpiration],
    asof: datetime | None = None,
) -> OptionExpiration | None:
    """Return the next monthly OG expiration with last trade >= asof."""
    if asof is None:
        asof = datetime.now(timezone.utc)
    asof_d = asof.date()
    future = []
    for e in expirations:
        try:
            ltd = datetime.strptime(e.last_trade_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if ltd >= asof_d:
            future.append((ltd, e))
    if not future:
        return None
    future.sort()
    return future[0][1]


def fetch_option_chain(
    driver: webdriver.Chrome,
    expiration: OptionExpiration,
    target: datetime | None = None,
) -> tuple[str, list[StrikeRow]]:
    """Fetch all strikes (call+put) for `expiration` and return (tradeDate, rows).

    Walks back up to 6 days from `target` until a non-empty settlement is found.
    """
    if target is None:
        target = datetime.now(timezone.utc)
    code = expiration.cme_code
    last_err: Exception | None = None
    for delta in range(0, 6):
        d = target - timedelta(days=delta)
        mdy = d.strftime("%m/%d/%Y")
        path = (f"/CmeWS/mvc/Settlements/Options/Settlements/"
                f"{expiration.product_id}/OOF?monthYear={code}&strategy=DEFAULT"
                f"&tradeDate={mdy}&isProtected")
        try:
            status, body = _fetch_json(driver, path)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if status != 200 or not isinstance(body, dict):
            continue
        rows_raw = body.get("settlements") or []
        if not rows_raw or body.get("empty"):
            continue
        # Build {strike: {call_oi, put_oi}}
        by_strike: dict[float, dict[str, int]] = {}
        for r in rows_raw:
            k = _f(r.get("strike"))
            if k is None:
                continue
            typ = (r.get("type") or "").lower()
            oi = _i(r.get("openInterest")) or 0
            slot = by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})
            if typ == "call":
                slot["call_oi"] = oi
            elif typ == "put":
                slot["put_oi"] = oi
        rows = [StrikeRow(strike=k, call_oi=v["call_oi"], put_oi=v["put_oi"])
                for k, v in sorted(by_strike.items())]
        return body.get("tradeDate", mdy), rows
    if last_err:
        raise last_err
    raise RuntimeError(f"no OG settlement found for {code} in past 6 days")


def most_active_by_volume(
    rows_with_volume: list[tuple[float, str, int]],
    n: int = 5,
) -> list[tuple[float, str, int]]:
    return sorted(rows_with_volume, key=lambda t: -t[2])[:n]


def chain_volume_summary(
    driver: webdriver.Chrome,
    expiration: OptionExpiration,
    target: datetime | None = None,
) -> list[tuple[float, str, int]]:
    """Return list of (strike, type, volume) for the requested expiration."""
    if target is None:
        target = datetime.now(timezone.utc)
    code = expiration.cme_code
    for delta in range(0, 6):
        d = target - timedelta(days=delta)
        mdy = d.strftime("%m/%d/%Y")
        path = (f"/CmeWS/mvc/Settlements/Options/Settlements/"
                f"{expiration.product_id}/OOF?monthYear={code}&strategy=DEFAULT"
                f"&tradeDate={mdy}&isProtected")
        status, body = _fetch_json(driver, path)
        if status != 200 or not isinstance(body, dict):
            continue
        rows_raw = body.get("settlements") or []
        if not rows_raw:
            continue
        out: list[tuple[float, str, int]] = []
        for r in rows_raw:
            k = _f(r.get("strike"))
            v = _i(r.get("volume")) or 0
            t = (r.get("type") or "").capitalize()
            if k is not None and v > 0:
                out.append((k, t, v))
        return out
    return []


if __name__ == "__main__":
    # Quick smoke test (requires CME_USERNAME/CME_PASSWORD env vars).
    from cme_login import ensure_logged_in, make_driver

    drv = make_driver()
    try:
        ensure_logged_in(drv)
        td_f, fut = fetch_gc_futures_settle(drv)
        print(f"Futures trade date: {td_f}, {len(fut)} contracts")
        front = front_active_future(fut)
        print(f"  Front: {front.month if front else '?'}  settle={front.settle if front else '?'}")

        exps = fetch_option_expirations(drv)
        print(f"Monthly OG expirations: {len(exps)}")
        for e in exps[:5]:
            print(f"  {e.label}  ltd={e.last_trade_date}  code={e.cme_code}")

        front_exp = front_monthly_expiration(exps)
        print(f"Front monthly: {front_exp}")
        if front_exp:
            td_o, rows = fetch_option_chain(drv, front_exp)
            print(f"Option chain trade date: {td_o}, {len(rows)} strikes")
            tot_call = sum(r.call_oi for r in rows)
            tot_put  = sum(r.put_oi for r in rows)
            print(f"  Total call OI: {tot_call:,}  Total put OI: {tot_put:,}")
            top_call = sorted(rows, key=lambda r: -r.call_oi)[:3]
            top_put  = sorted(rows, key=lambda r: -r.put_oi)[:3]
            print("  Top call OI:")
            for r in top_call:
                print(f"    {r.strike:>8}  call_oi={r.call_oi:>7,}  put_oi={r.put_oi:,}")
            print("  Top put OI:")
            for r in top_put:
                print(f"    {r.strike:>8}  put_oi ={r.put_oi:>7,}  call_oi={r.call_oi:,}")
    finally:
        drv.quit()
