# Signal Desk APK, phone-only steps

1. github.com > sign in > + > New repository > name: signal-desk > Private > Create.
2. Tap "uploading an existing file". Upload these 7 files:
   index.html, manifest.webmanifest, sw.js, icon-192.png, icon-512.png,
   package.json, capacitor.config.json. Tap Commit changes.
3. Add file > Create new file. In the name box type exactly:
   .github/workflows/build-apk.yml
   Open build-apk.yml from this folder in any text app, copy all of it,
   paste into the big box, tap Commit changes.
4. Open the Actions tab > Build APK > Run workflow > Run workflow.
5. Wait about 5 minutes for a green tick. Tap the run.
6. At the bottom under Artifacts, tap signal-desk-apk. A zip downloads.
7. Unzip it. Tap app-debug.apk to install (allow "Install unknown apps").
8. In the app: Settings > paste your free Twelve Data key > Save >
   Turn on notifications > Send a test notification.

If the run shows a red cross, open it, open the failing step, copy the error and send it to Claude.
