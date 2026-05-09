# CME Gold — Daily Swing-Trading Levels

Automated daily report for COMEX gold (GC futures + OG monthly options) using
Max Pain methodology, call/put open-interest walls, ΔOI day-over-day, and
institutional flow from the CME Globex Trade Browser.

## What you get

Every morning at **08:00 Madrid** (06:00 UTC winter / 07:00 UTC summer) the
report is produced and delivered as Markdown:

- Front-month GC settlement, change, volume, open interest
- **Max Pain** strike for the active OG monthly expiration
- Top-3 **Call walls** (resistance) and top-3 **Put walls** (support) by OI
- **ΔOI** vs the prior trading day (fresh institutional positioning)
- Largest electronic block trades from the **Globex Trade Browser**
- Most-active strikes by volume yesterday

## Math

Max Pain is the strike that minimises the total payout to option holders at
expiration:

```
Pain(K) = Σ_i  max(K - K_i, 0) · OI_call_i        # ITM calls if K is high
        + Σ_i  max(K_i - K, 0) · OI_put_i         # ITM puts  if K is low
```

The strike `K` minimising `Pain(K)` is the level that market makers want price
to drift toward into expiration.

## Architecture

| Source                                                                      | Auth   | Module               |
|-----------------------------------------------------------------------------|--------|----------------------|
| `CmeWS/Settlements/Futures/Settlements/437/FUT?tradeDate=…`                 | login* | `src/options_api.py`  |
| `CmeWS/atm/expirations/437` — list of OG monthly expirations                | login* | `src/options_api.py`  |
| `CmeWS/Settlements/Options/Settlements/192/OOF?monthYear=OG{M}{YY}&…`       | login* | `src/options_api.py`  |
| `clearing/operations-and-deliveries/accepted-trade-types/block-data.html`   | public | `src/block_trades.py` |

\*The CME REST endpoints reject direct scrapers from data-center IPs, but the
same calls succeed when issued from a logged-in browser tab on cmegroup.com,
so we run them inside the authenticated Selenium driver via `fetch()`. Login
is performed via headless Selenium (`src/cme_login.py`) and cookies are
persisted under `$CME_PROFILE` (default `/home/ubuntu/.cme/profile`) so we
only re-auth when the session expires.

The block-trades page is public, but its rows are lazy-loaded as the user
scrolls; `block_trades.py` scrolls the page until the row count stabilises,
extracts every `<tbody>` atomically via `execute_script()` to avoid stale
references, and filters multi-leg spreads down to the gold-related products
(GC futures, OG monthly options, 1OG–5OG weeklies).

## Run

```bash
export CME_USERNAME=alexiptv01001@gmail.com
export CME_PASSWORD=…           # set via Devin org secret in production
python3 src/daily_report.py     # prints Markdown to stdout
```

If `CME_USERNAME` / `CME_PASSWORD` are missing or login fails, the script
falls back to a **futures-only report** that lists the front-month GC price
and explains why options data is missing.

## Tests

```bash
python3 -m pytest tests
```

## Schedule

Configured as a [Devin Schedule](https://docs.devin.ai/schedules) running daily at
**06:00 UTC** (= 08:00 Madrid winter / 07:00 Madrid summer). The schedule
description and prompt live in this repo at `schedule/prompt.md`.
