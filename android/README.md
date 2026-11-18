# Recipe Importer (Android)

Native Android app (Kotlin, Jetpack Compose). Share a Facebook/YouTube link to it and it calls the backend.

## Get the APK
1. Open the repository's **Actions** tab on GitHub and choose the latest successful **Android build** run.
2. Download the `recipe-importer-debug-apk` artifact (a zip) and unzip it to get `app-debug.apk`.

## Install
1. Copy the APK to your phone (or download it there directly).
2. Open it from the browser or Files app; when prompted, allow "Install unknown apps" for that app.
3. Confirm the install.

## Configure
Open the app settings and enter:
- **Backend URL**: your Render service URL (https).
- **App token**: the backend's `APP_TOKEN` value.
- **Gemini key** (optional).
