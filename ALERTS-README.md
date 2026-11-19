# Meridian Signal alerts (pings when the app is closed)

Runs on GitHub every 5 minutes (Monday to Friday) and pushes a message to your phone the moment a trade turns Ready.

## One-time setup (about 5 minutes)
1. Install the free **ntfy** app from the Play Store. Open it, tap +, and subscribe to the topic shown in Meridian Signal > Settings > "Pings when the app is closed". Tap "Send test ping" in the app to check it works.
2. In your GitHub repo: Settings > Secrets and variables > Actions > New repository secret.
   - `TWELVEDATA_KEY` = your Twelve Data key
   - `NTFY_TOPIC` = the topic from the app
3. Pick your timeframes: Variables tab > New variable `INTERVAL` = one or several of `1min`, `5min`, `15min`, `30min`, `1h`, `4h`, `1day`, `1week`, separated by commas, for example `5min,15min,1h`. The app has a "Copy my timeframes" button that gives you this. If you skip it, it uses `15min`. The check runs every 5 minutes, but only does real work when a new candle has closed.
4. Optional: Variables tab > New variable `PAIRS` = the list from "Copy my pair list" in the app, so the alerts watch the same pairs. Leave it out to watch the 6 default pairs.
5. Upload `forex_alerts.py` to the main page of the repo.
6. Add file > Create new file, name it `.github/workflows/alerts.yml` (no trailing dot) and paste in `workflow-alerts.yml`.
7. Actions > Forex alerts > Run workflow to test.

Telegram still works if you set `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` instead.

No signal is guaranteed. Not financial advice.

Data budget: a free Twelve Data key allows 800 calls a day. M1 needs about 1,440 a day per pair and M5 about 288, so use M15 or longer for several pairs, or M1/M5 for one or two.
