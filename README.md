# Meridian Signal: everything in one zip

Upload layout:
- index.html, sw.js, manifest.webmanifest, icon-192.png, icon-512.png, capacitor.config.json, package.json, forex_alerts.py  -> main page of the repo
- .github/workflows/build-apk.yml and alerts.yml  -> inside .github/workflows/

GitHub secrets: TWELVEDATA_KEY, NTFY_TOPIC
GitHub variables: INTERVAL (e.g. 5min,15min,1h), PAIRS (optional). Both have a Copy button in the app, in Settings.

After the build: uninstall the old app, install the new one. Settings must show 'Meridian Signal v3.3' at the bottom.
No signal is guaranteed. Not financial advice.
