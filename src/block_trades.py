"""Block-trades scraper for CME's public Block Data page.

CME publishes the same dataset that powers the QuikStrike "Globex Trade
Browser" tool at:
    https://www.cmegroup.com/clearing/operations-and-deliveries/accepted-trade-types/block-data.html

The page is rendered server-side as a giant HTML table (one tbody per
trade; spreads use multi-row spans for time / type / product cells).  We
materialise the table via JavaScript inside an authenticated Selenium
session and filter for gold-related products.

Public API
----------
fetch_gold_blocks(driver) -> list[BlockTrade]
    Return today's gold block trades (futures + options) ordered by
    quantity descending.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from selenium.webdriver.remote.webdriver import WebDriver

BLOCK_URL = ("https://www.cmegroup.com/clearing/operations-and-deliveries/"
             "accepted-trade-types/block-data.html")

# JavaScript executed inside the page to atomically read every trade
# row.  Each <tbody> in `table.block-trades-table` represents one trade
# (an outright or a multi-leg spread).  We pull every <td>'s innerText
# and group by tbody so we can correctly attribute legs to a trade.
EXTRACT_JS = r"""
const out = [];
const tbodies = document.querySelectorAll('table.block-trades-table tbody');
for (const tb of tbodies) {
    const trade_rows = [];
    for (const tr of tb.querySelectorAll('tr')) {
        const cells = Array.from(tr.querySelectorAll('td'))
                           .map(td => td.innerText.trim());
        if (cells.length) trade_rows.push(cells);
    }
    if (trade_rows.length) out.push(trade_rows);
}
return out;
"""


@dataclass
class BlockTradeLeg:
    """One leg of a block trade (outright trade has a single leg)."""
    product: str        # e.g. "Gold Option"
    sym: str            # e.g. "OGM7"
    qty: int            # contracts
    cp_strike: str      # "C7500.00" / "P4400.00" / "" for futures
    side: str           # "Buy" or "Sell"
    price: float


@dataclass
class BlockTrade:
    """One block trade (outright or multi-leg spread)."""
    time_ct: str        # "11:29:29 AM"
    trade_type: str     # "Future", "Option", or "Spread"
    legs: list[BlockTradeLeg] = field(default_factory=list)
    net_price: Optional[float] = None
    spread_qty: Optional[int] = None    # for spreads, the trade size

    @property
    def total_contracts(self) -> int:
        """Sum of leg quantities (a 100-lot spread of 2 legs = 200)."""
        return sum(leg.qty for leg in self.legs)

    @property
    def primary_leg(self) -> Optional[BlockTradeLeg]:
        """Largest leg by quantity — used for ranking / display."""
        return max(self.legs, key=lambda l: l.qty) if self.legs else None


_GOLD_KEYWORDS = ("Gold Future", "Gold Option", "1OG", "2OG", "3OG", "4OG",
                  "5OG", "Comex Gold")


def _is_gold_row(text: str) -> bool:
    return any(k in text for k in _GOLD_KEYWORDS)


def _parse_qty(s: str) -> int:
    s = (s or "").replace(",", "").strip()
    try:
        return int(s)
    except ValueError:
        return 0


def _parse_price(s: str) -> Optional[float]:
    s = (s or "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_trade(rows: list[list[str]]) -> Optional[BlockTrade]:
    """Convert a tbody's rows (one per leg) into a BlockTrade.

    The first row of every tbody contains:
        [TIME] [TYPE] [PRODUCT] [SYM] [NET_PRICE_or_blank] [QTY] [C/P_STRIKE] [B/S] [PRICE]
    Subsequent leg rows omit the rowspan'd cells (TIME/TYPE/NET_PRICE):
        [PRODUCT] [SYM] [QTY] [C/P_STRIKE] [B/S] [PRICE]
    """
    if not rows:
        return None
    first = rows[0]
    if len(first) < 7:
        return None

    time_ct = first[0]
    trade_type = first[1]

    bt = BlockTrade(time_ct=time_ct, trade_type=trade_type)

    if trade_type == "Spread":
        # Header row: TIME, TYPE, PRODUCT, SYM, NET_PRICE, QTY, ...
        # Some spreads have NET_PRICE blank → cell index shift.
        # Detect by trying to parse cell[4] as float.
        bt.net_price = _parse_price(first[4]) if len(first) >= 5 else None
        bt.spread_qty = _parse_qty(first[5]) if len(first) >= 6 else None
        # First leg starts at offset 2 (PRODUCT, SYM)
        leg = _parse_leg(first[2:])
        if leg: bt.legs.append(leg)
        for r in rows[1:]:
            leg = _parse_leg(r)
            if leg: bt.legs.append(leg)
    else:
        # Outright: TIME, TYPE, PRODUCT, SYM, NET_PRICE_or_blank, QTY, C/P_STRIKE, B/S, PRICE
        bt.net_price = _parse_price(first[4]) if len(first) >= 5 else None
        leg = _parse_leg(first[2:])
        if leg: bt.legs.append(leg)
    return bt if bt.legs else None


def _parse_leg(cells: list[str]) -> Optional[BlockTradeLeg]:
    """Parse a leg starting at PRODUCT cell.

    Layout: [PRODUCT] [SYM] [NET_PRICE_or_blank?] [QTY] [C/P_STRIKE] [B/S] [PRICE]
    """
    if len(cells) < 5:
        return None
    product = cells[0]
    sym = cells[1]
    # Net price may be blank for individual legs of a spread; if cell[2]
    # has a digit and cell[3] also has a digit, cell[2] is net price.
    if len(cells) >= 7:
        # Outright form with NET_PRICE column.
        try:
            qty = _parse_qty(cells[3])
            cp_strike = cells[4]
            side = cells[5]
            price = _parse_price(cells[6]) or 0.0
        except (IndexError, ValueError):
            return None
    else:
        # Spread leg form (no net price column).
        try:
            qty = _parse_qty(cells[2])
            cp_strike = cells[3]
            side = cells[4]
            price = _parse_price(cells[5]) or 0.0
        except (IndexError, ValueError):
            return None
    if qty <= 0:
        return None
    return BlockTradeLeg(product=product, sym=sym, qty=qty,
                         cp_strike=cp_strike, side=side, price=price)


def fetch_gold_blocks(driver: WebDriver) -> list[BlockTrade]:
    """Load the public block-trades page and return today's gold trades.

    Caller must pass an already-logged-in driver (cme_login.ensure_logged_in).
    Trades are ranked by total_contracts descending (largest first).

    The block-trades table is lazy-loaded — rows materialise as the user
    scrolls down.  We scroll repeatedly until the row count stabilises.
    """
    driver.set_page_load_timeout(60)
    try:
        driver.get(BLOCK_URL)
    except Exception:
        # Slow-loading page — proceed; data may still be in DOM.
        pass
    time.sleep(12)

    # Scroll-and-wait until row count stops growing.
    last_count = -1
    for cycle in range(6):
        for _ in range(20):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.25)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        n = driver.execute_script(
            "return document.querySelectorAll('table.block-trades-table tbody').length;")
        if n == last_count:
            break
        last_count = n

    tbodies = driver.execute_script(EXTRACT_JS)
    if not tbodies:
        time.sleep(6)
        tbodies = driver.execute_script(EXTRACT_JS)

    trades: list[BlockTrade] = []
    for tb in tbodies:
        joined = " ".join(c for row in tb for c in row)
        if not _is_gold_row(joined):
            continue
        bt = _parse_trade(tb)
        if bt and bt.legs:
            trades.append(bt)

    trades.sort(key=lambda b: b.total_contracts, reverse=True)
    return trades


# Russian translations for display only (data layer keeps English keys).
_SIDE_RU = {"Buy": "Покупка", "Sell": "Продажа"}
_TYPE_RU = {"Future": "Фьючерс", "Option": "Опцион", "Spread": "Спред",
            "Strip": "Стрип"}


def _ru_side(s: str) -> str:
    return _SIDE_RU.get(s, s)


def _ru_type(t: str) -> str:
    return _TYPE_RU.get(t, t)


def render_blocks_md(trades: list[BlockTrade], top_n: int = 5) -> str:
    """Render the top-N gold block trades as a Markdown bullet list."""
    if not trades:
        return "_Сегодня крупных блок-сделок по золоту не зафиксировано._"
    lines = []
    for bt in trades[:top_n]:
        if bt.trade_type == "Spread" and len(bt.legs) > 1:
            legs_txt = " / ".join(
                f"{_ru_side(l.side)} {l.qty} {l.sym} {l.cp_strike}".strip()
                for l in bt.legs)
            head = f"- **{_ru_type(bt.trade_type)}** ({bt.time_ct} CT)"
            if bt.net_price is not None:
                head += f" нетто **{bt.net_price}**"
            if bt.spread_qty:
                head += f"  •  размер **{bt.spread_qty}**"
            lines.append(head + ": " + legs_txt)
        else:
            leg = bt.primary_leg
            if leg is None: continue
            tag = leg.cp_strike if leg.cp_strike else "аутрайт"
            lines.append(
                f"- **{_ru_type(bt.trade_type)}** ({bt.time_ct} CT): "
                f"{_ru_side(leg.side)} **{leg.qty}** {leg.sym} {tag} @ "
                f"{leg.price}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/ubuntu/cme_gold/src")
    from cme_login import make_driver, ensure_logged_in
    drv = make_driver(headless=True)
    try:
        ensure_logged_in(drv)
        trades = fetch_gold_blocks(drv)
        print(f"# Gold block trades today: {len(trades)}\n")
        print(render_blocks_md(trades, top_n=10))
    finally:
        drv.quit()
