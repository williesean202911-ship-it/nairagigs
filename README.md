# Meridian Signal

Forex signal app with an interactive chart. Builds into an Android APK on GitHub Actions.

1. Upload every file in this folder to your GitHub repo (keep `build-apk.yml` inside `.github/workflows/`).
2. Actions > Build APK > Run workflow. When it is green, download the `meridian-signal-apk` artifact and unzip it.
3. Install app-debug.apk. It installs as a NEW app called Meridian Signal, next to the old one.
4. Open Settings, paste your Twelve Data key, tap Allow notifications, then "Send a test notification".

Demo data is not real prices. No signal is guaranteed.
