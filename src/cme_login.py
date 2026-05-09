"""CME Group login helper.

Logs in once via Selenium and stores cookies for re-use.  Subsequent runs
restore cookies and only re-login if they have expired.

Credentials are read from environment variables (set from Devin secrets):
    CME_USERNAME = registered email (e.g. alexiptv01001@gmail.com)
    CME_PASSWORD = registered password
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CHROME_BIN  = os.environ.get(
    "CME_CHROME_BIN",
    "/opt/.devin/playwright_browsers/chromium-1097/chrome-linux/chrome",
)
DRIVER_BIN  = os.environ.get(
    "CME_CHROMEDRIVER",
    "/home/ubuntu/.cme/chromedriver-linux64/chromedriver",
)
PROFILE_DIR = Path(os.environ.get("CME_PROFILE", "/home/ubuntu/.cme/profile"))
COOKIES_FILE = Path(os.environ.get("CME_COOKIES", "/home/ubuntu/.cme/cookies.json"))

LOGIN_URL = "https://login.cmegroup.com/sso/navmenu.action"  # redirects to showAuth
HOME_URL  = "https://www.cmegroup.com/"


def make_driver(headless: bool = True) -> webdriver.Chrome:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    opts = Options()
    opts.binary_location = CHROME_BIN
    args = [
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu", "--window-size=1400,900",
        f"--user-data-dir={PROFILE_DIR}",
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]
    if headless:
        args.append("--headless=new")
    for a in args:
        opts.add_argument(a)
    svc = Service(DRIVER_BIN, log_output="/tmp/chromedriver.log")
    return webdriver.Chrome(service=svc, options=opts)


def save_cookies(driver: webdriver.Chrome) -> None:
    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cookies = driver.get_cookies()
    COOKIES_FILE.write_text(json.dumps(cookies))


def load_cookies(driver: webdriver.Chrome) -> bool:
    if not COOKIES_FILE.exists():
        return False
    try:
        cookies = json.loads(COOKIES_FILE.read_text())
    except Exception:
        return False
    # Cookies must be set under matching domain — visit the home page first.
    driver.get(HOME_URL)
    for c in cookies:
        try:
            driver.add_cookie({k: v for k, v in c.items()
                               if k in {"name", "value", "domain", "path",
                                         "secure", "expiry", "sameSite"}})
        except Exception:
            pass
    return True


def is_logged_in(driver: webdriver.Chrome) -> bool:
    """Heuristic: load CME home and look for 'Log Out' or username text."""
    driver.get(HOME_URL)
    time.sleep(3)
    # CME pages show 'Log Out' / 'My Profile' in the top nav when authenticated.
    src = driver.page_source.lower()
    return "log out" in src or "logout" in src or "my profile" in src


def perform_login(driver: webdriver.Chrome, email: str, password: str) -> None:
    """Submit login form on login.cmegroup.com.

    The form uses element ids `user` and `pwd` (not `username`/`password`).
    Submission is intercepted by JavaScript; pressing Enter from the password
    field works most reliably.
    """
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.ID, "user")))
    time.sleep(1)
    e = driver.find_element(By.ID, "user")
    e.clear(); e.send_keys(email)
    p = driver.find_element(By.ID, "pwd")
    p.clear(); p.send_keys(password)
    # Try submit button first; fall back to Enter key.
    submitted = False
    for sel in ("#loginSubmit", "button[type=submit]", "input[type=submit]",
                "#submitButton", ".btn-primary"):
        elts = driver.find_elements(By.CSS_SELECTOR, sel)
        if elts:
            try:
                driver.execute_script("arguments[0].click();", elts[0])
                submitted = True
                break
            except Exception:
                continue
    if not submitted:
        from selenium.webdriver.common.keys import Keys
        p.send_keys(Keys.RETURN)
    # Wait for redirect away from the auth page.
    for _ in range(30):
        time.sleep(1)
        if "showAuth" not in driver.current_url and "login.cmegroup.com" not in driver.current_url:
            break


def login_with_cookies(driver: webdriver.Chrome) -> bool:
    """Try to restore an existing session.  Returns True if logged in."""
    if not load_cookies(driver):
        return False
    return is_logged_in(driver)


def ensure_logged_in(driver: webdriver.Chrome) -> None:
    """Restore cookies if possible, otherwise full login + persist cookies."""
    if login_with_cookies(driver):
        return
    email = os.environ["CME_USERNAME"]
    pw    = os.environ["CME_PASSWORD"]
    perform_login(driver, email, pw)
    if not is_logged_in(driver):
        raise RuntimeError("CME login failed — please check credentials/captcha")
    save_cookies(driver)


if __name__ == "__main__":
    drv = make_driver()
    try:
        ensure_logged_in(drv)
        print("Logged in OK; current URL:", drv.current_url)
    finally:
        drv.quit()
