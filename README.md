# selfupdate

Selfso Android Over-The-Air (OTA) update library, static web distribution portal, and publishing automation tooling.

Copyright (C) 2026, Charles Chiou

---

## 1. Overview & Architecture

`selfupdate` is a first-party, unversioned shared Android library and distribution toolkit designed for personal Android applications (`aimon`, `robohero`, `octi`, `nigosh`). It powers off-market direct distribution via static HTTP/HTTPS hosting:

- **Static Distribution Portal**: Hosted under `https://www.selfso.com/software/android/`, providing static HTML catalog and app detail pages, downloadable APK binaries, and cryptographic `version.json` manifests.
- **Android Runtime Library (`com.selfso.selfupdate`)**: Lightweight in-app update checker and installer that polls `version.json`, verifies streaming SHA-256 digests, and initiates in-place package installations via Android's `PackageInstaller` Session API.
- **Publishing Automation (`scripts/`)**: CLI tools to inspect built APK binaries (`aapt2` and AGP `output-metadata.json`), calculate SHA-256 digests, stage files to the web portal directory, update both master and single-app `version.json` manifests, and regenerate static HTML pages styled with `selfso.com`'s Zen / Editorial Paper design system.

### Architectural Diagram

```text
  +-------------------------------------------------------+
  |                   Build Machine                       |
  |  [Compiled APK]                                       |
  |         |                                             |
  |         v                                             |
  |  [scripts/publish_android_apk.py]                     |
  |         |                                             |
  |         +---> [~/work/www/selfso/html/software/android/]
  |                   |-- index.html                      |
  |                   |-- version.json (master catalog)   |
  |                   \-- <slug>/                         |
  |                         |-- index.html                |
  |                         |-- version.json (single app) |
  |                         \-- <slug>.apk                |
  +-------------------------------------------------------+
                            | (rsync / static web)
                            v
  +-------------------------------------------------------+
  |       Web Portal: https://www.selfso.com/             |
  +-------------------------------------------------------+
                            | (HTTPS GET)
                            v
  +-------------------------------------------------------+
  |                   Android Client                      |
  |  [SelfUpdateChecker]  (polls version.json)            |
  |         |                                             |
  |         v (if versionCode > installed)                |
  |  [ApkDownloader]      (SHA-256 streaming verify)     |
  |         |                                             |
  |         v                                             |
  |  [ApkInstaller]       (PackageInstaller.Session)      |
  |         |                                             |
  |  [SelfUpdateBanner / SelfUpdateDialog] (Compose UI)   |
  +-------------------------------------------------------+
```

---

## 2. Manifest Specifications (`version.json`)

The update system uses a dual-schema manifest design:

### 2.1 Master Multi-App Catalog (`https://www.selfso.com/software/android/version.json`)

```json
{
  "schemaVersion": 1,
  "baseUrl": "https://www.selfso.com/software/android/",
  "updatedAt": "2026-10-22T09:15:00Z",
  "apps": {
    "com.selfso.octi": {
      "slug": "octi",
      "title": "OCTI Strategy Game",
      "applicationId": "com.selfso.octi",
      "versionCode": 20002,
      "versionName": "2.0.2",
      "minSdk": 24,
      "targetSdk": 35,
      "apkUrl": "https://www.selfso.com/software/android/octi/octi.apk",
      "pageUrl": "https://www.selfso.com/software/android/octi/",
      "sha256": "3a8b4c...",
      "sizeBytes": 5412890,
      "publishedAt": "2026-10-22T09:15:00Z",
      "releaseNotes": "OCTI abstract strategy board game and minimax AI engine for Android."
    }
  }
}
```

### 2.2 Per-App Single Manifest (`https://www.selfso.com/software/android/<slug>/version.json`)

The per-app manifest contains the single app's manifest object directly at the JSON root:

```json
{
  "slug": "octi",
  "title": "OCTI Strategy Game",
  "applicationId": "com.selfso.octi",
  "versionCode": 20002,
  "versionName": "2.0.2",
  "minSdk": 24,
  "targetSdk": 35,
  "apkUrl": "https://www.selfso.com/software/android/octi/octi.apk",
  "pageUrl": "https://www.selfso.com/software/android/octi/",
  "sha256": "3a8b4c...",
  "sizeBytes": 5412890,
  "publishedAt": "2026-10-22T09:15:00Z",
  "releaseNotes": "OCTI abstract strategy board game and minimax AI engine for Android."
}
```

### 2.3 Dual-Schema Resolution Logic

When `com.selfso.selfupdate` checks an update endpoint:
1. If the URL ends with `/`, it appends `version.json`.
2. It fetches the JSON payload via standard `HttpsURLConnection`.
3. If the payload contains an `"apps"` dictionary, it looks up the running app by `context.packageName` (and automatically falls back to `context.packageName.removeSuffix(".debug")`).
4. If `"apps"` is not present, it parses the root object directly as a single-app manifest.
5. If `apkUrl` is relative, it resolves it against `manifestUrl`.
6. An update is offered only when `remote.versionCode > installedVersionCode`.

---

## 3. Consumer Android App Integration

### 3.1 Mounting the Library Module

In the host application's `settings.gradle.kts`:

```kotlin
// Mount :selfupdate module from shared workspace or submodule
include(":selfupdate")
project(":selfupdate").projectDir = file("../../selfupdate/android") // or relative path
```

### 3.2 Adding the Dependency

In the host application's module `build.gradle.kts`:

```kotlin
dependencies {
    implementation(project(":selfupdate"))
}
```

### 3.3 Adding Required Permissions

In `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
```

### 3.4 Jetpack Compose UI Integration

In your main screen or top-level layout:

```kotlin
val context = LocalContext.current
val controller = remember { SelfUpdateController(context) }
val updateState by controller.state.collectAsState()

LaunchedEffect(Unit) {
    controller.checkForUpdates()
}

// Option A: Non-intrusive top banner
SelfUpdateBanner(
    state = updateState,
    onDownloadClick = { controller.downloadAndInstall() },
    onDismiss = { controller.dismiss() }
)

// Option B: Detailed modal dialog
SelfUpdateDialog(
    state = updateState,
    onDownloadClick = { controller.downloadAndInstall() },
    onDismiss = { controller.dismiss() }
)
```

---

## 4. Publishing CLI Tools

### 4.1 Generating Manifest Metadata (`scripts/gen_version_json.py`)

Inspects an `.apk` file, parses badging metadata via `aapt2` or AGP `output-metadata.json`, computes the SHA-256 digest, and emits JSON:

```bash
python3 scripts/gen_version_json.py --apk path/to/app-release.apk --slug octi --title "OCTI Strategy Game"
```

### 4.2 Publishing APKs to Web Portal (`scripts/publish_android_apk.py`)

Publishes an APK into the local static web directory:
- Copies the APK to `<web-root>/<slug>/<apkFilename>`.
- Generates `<web-root>/<slug>/version.json`.
- Updates the master multi-app catalog `<web-root>/version.json`.
- Renders `<web-root>/<slug>/index.html` and `<web-root>/index.html` using `selfso.com`'s `/css/main.css` styling.

Publish a single app:

```bash
python3 scripts/publish_android_apk.py --slug octi --apk path/to/app-release.apk
```

Publish all known apps across personal projects:

```bash
python3 scripts/publish_android_apk.py --publish-all
```
