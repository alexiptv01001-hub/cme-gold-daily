# Daily prompt for the CME Gold report

Run the daily CME gold swing-trading report.

1. Activate the saved playbook **"daily-cme-gold-report"** if not already
   active (it captures the full procedure).
2. Pull the latest version of this repo.
3. `python3 src/daily_report.py` and post the resulting Markdown back to
   the user as the message body of this session.
4. If the script falls back to "futures-only" mode (CME login expired,
   captcha, network error), include the failure note and request a manual
   re-login from the user.
