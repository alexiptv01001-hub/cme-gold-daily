# Daily prompt for the CME Gold report

Run the daily CME gold swing-trading report. Activate the playbook
`!gold_daily` ("Daily CME Gold Swing-Trading Report") and follow it.

In short:
1. Confirm `CME_USERNAME` and `CME_PASSWORD` are set in the environment
   (saved as user-scoped Devin secrets); abort with a clear note if not.
2. Pull the latest `main` of `alexiptv01001-hub/cme-gold-daily`.
3. From the repo root run `python3 src/daily_report.py` and capture
   stdout — that is the full Markdown report.
4. Verify the output contains every required section: `# Gold (GC)`,
   `Max Pain`, `Call walls`, `Put walls`, `Most Active`,
   `Globex Trade Browser`, `Suggested swing levels`. If any section is
   missing, re-run once after deleting `/home/ubuntu/.cme/cookies.json`.
5. Post the Markdown back to me as the **only** message body of this
   scheduled session — no preamble, no edits, just the raw report.
6. If the script falls back to "futures-only" mode, post that report
   along with a one-line note on what failed (login expired, captcha,
   network error) and ask me to re-auth manually next time.

Do not commit anything to git or start a new PR.
