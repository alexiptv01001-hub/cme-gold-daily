"""QuikStrike CME Globex Trade Browser scraper for electronic option trades.

Status (2026-05-10): the public landing page

    https://www.cmegroup.com/tools-information/quikstrike/cme-globex-trade-browser.html

embeds the QuikStrike app via a JS-injected ``<iframe>``.  The host
page reads the user's session via ``window.cmeAjax.loginPromise`` and
then patches ``<iframe[src*='cmegroup-tools']>`` with the QuikStrike
URL.  Two practical blockers exist for a headless scraper:

1. ``cmeAjax.isLoggedIn`` is **false** even when our SSO session is
   valid (the host page makes a separate async call to set
   ``loginInfo``; in headless Chrome it never resolves).
2. The page has an invisible reCAPTCHA (``size=invisible``).  CME's
   bot-detection auto-blocks if reCAPTCHA fails — and headless Chrome
   reliably fails it.

We tried these workarounds and confirmed they do not work:
- forcing ``window.updateIframe()`` after a long wait
- swapping the QuikStrike ``viewitemid`` query string parameter to
  ``GlobexTradeBrowser`` / ``OptionTradeBrowser`` / similar slugs
- visiting candidate URLs at ``cmegroup.quikstrike.net`` directly

Until either CME exposes a public JSON endpoint for electronic trades
or we attach via a real (non-headless) browser session for one-time
captcha solve, this scraper returns an empty list and the daily
report falls back to the (much higher signal) block-trade flow.

If you want to iterate on this:
- look at ``/home/ubuntu/.cme/probe_gtb*.py`` for the reverse-engineering
  context
- the path forward is probably to attach Selenium to an external
  Chrome instance the user logged into manually (the cookie + reCAPTCHA
  cookie persist for ~24 h)
"""
from __future__ import annotations

from selenium.webdriver.remote.webdriver import WebDriver

from trades import TradeRecord


def fetch_gold_electronic_trades(driver: WebDriver) -> list[TradeRecord]:
    """Return today's electronic gold-option trades from the Globex Trade
    Browser.

    Currently always returns an empty list (see module docstring).  The
    caller is expected to fall back to block trades for institutional
    flow analysis.
    """
    return []
