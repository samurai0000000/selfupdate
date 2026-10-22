# selfupdate

Selfso Over-The-Air (OTA) and desktop self-update libraries, static web distribution portals, and automated publishing tooling for Android (`android/`) and Windows C++ / Qt6 (`windows/`).

Copyright (C) 2026, Charles Chiou

---

## 1. Overview & Architecture

`selfupdate` is a first-party, zero-dependency self-update engine and distribution toolkit designed for personal applications across Android and Windows (`aimon`, `robohero`, `octi`, `nigosh`):

- **Android OTA Library (`com.selfso.selfupdate`)**: In-app update engine (`android/`) using Android's `PackageInstaller` Session API and Jetpack Compose UI components, distributed via `https://www.selfso.com/software/android/`.
- **Windows C++ / Qt6 Library (`namespace selfupdate`)**: Zero-dependency C++17 library (`windows/`) using native Win32 WinHTTP (POSIX socket fallback on Linux), RFC 6234 SHA-256 verification, detached PID-wait setup installer execution or atomic `.old` in-place binary copy, and an optional header-only Qt6 GUI thread-marshaling bridge (`QtSelfUpdateBridge.hxx`), distributed via `https://www.selfso.com/software/windows/`.
- **Static Distribution Portals**: Pure static HTML distribution portals hosted on `selfso.com` providing browsable catalogs, app detail pages, downloadable binaries, and cryptographic `version.json` manifests.
- **Automated Publishing Tooling (`scripts/`)**: CLI tools to inspect built APKs (`aapt2`) or Windows executables (PE header & `.rsrc` `RT_VERSION` parsing), stage binaries into static web directories, update per-app and master `version.json` manifests non-destructively, and generate static HTML pages.

---

## 2. Windows C++ / Qt6 Integration (`windows/`)

### 2.1 Source-Level CMake Integration (`windows/selfupdate.cmake`)

Consumer Windows C++ applications compile `selfupdate` directly from source without requiring prebuilt library binaries or third-party dependencies (`Qt6Network`, OpenSSL, and external JSON libraries are **not** required).

In the host application's `CMakeLists.txt`:

```cmake
# Include selfupdate CMake module from relative path
include("${CMAKE_CURRENT_SOURCE_DIR}/../../selfupdate/windows/selfupdate.cmake")

# Attach selfupdate C++17 sources, include directories, and Win32 platform libraries
selfupdate_target_sources(my_app_target)
```

`selfupdate.cmake` automatically configures:
- Sources: `UpdateManifest.cxx`, `UpdateState.cxx`, `Sha256.cxx`, `HttpTransport.cxx`, `SelfUpdateChecker.cxx`, `PackageDownloader.cxx`, `UpdateInstaller.cxx`, `SelfUpdateController.cxx`.
- Includes: `windows/include/` (`#include <selfupdate/SelfUpdateController.hxx>`).
- Platform Libraries: links `winhttp`, `version`, `shell32`, `ole32`, `advapi32` on Windows, and `Threads::Threads` on POSIX.

### 2.2 Host Application Lifecycle & Qt6 GUI Bridge

`SelfUpdateController` runs update checks and downloads asynchronously on a worker thread. For Qt6 applications, `QtSelfUpdateBridge.hxx` safely marshals background `UpdateState` transitions to the Qt GUI event loop via `QMetaObject::invokeMethod(..., Qt::QueuedConnection)`:

```cpp
#include <selfupdate/SelfUpdateController.hxx>
#include <selfupdate/QtSelfUpdateBridge.hxx>
#include <QCoreApplication>
#include <QMessageBox>

// Initialize controller with app configuration
selfupdate::CheckerConfig config;
config.applicationId = "com.selfso.octi";
config.slug = "octi";
config.manifestUrl = "https://www.selfso.com/software/windows/";

auto controller = std::make_shared<selfupdate::SelfUpdateController>(config);

// Bind Qt GUI thread marshaling and quit callback
selfupdate::bindQtController(controller, qApp, [](const selfupdate::UpdateState& state) {
    if (state.phase == selfupdate::UpdatePhase::Available) {
        // Prompt user on Qt GUI thread
        auto reply = QMessageBox::question(
            nullptr, "Update Available",
            QString("A new version (%1) is available. Download and update now?")
                .arg(QString::fromStdString(state.manifest.versionName)));
        if (reply == QMessageBox::Yes) {
            // Initiate streaming download and installation
        }
    } else if (state.phase == selfupdate::UpdatePhase::Downloading) {
        // Update download progress dialog or status bar
        int percent = state.percent();
    } else if (state.phase == selfupdate::UpdatePhase::Relaunching) {
        // Host app will quit as the update trampoline hands off execution
    }
});

// Trigger startup update check (non-blocking)
controller->checkForUpdates(/* isManualCheck */ false);
```

### 2.3 Install Modes & File-Lock Safety

Windows prohibits overwriting the binary file of an active process (`ERROR_SHARING_VIOLATION`). `UpdateInstaller` handles this transparently:
1. **Setup Installers (`InstallMode::Installer`)**: Launches a detached PID-wait trampoline (`selfupdate_trampoline.cmd`) that waits for the host PID to exit, executes the setup executable with silent arguments (`/S` or `--silent`), and relaunches the application.
2. **Binary Copy (`InstallMode::BinaryCopy`)**: Renames the running `<app>.exe` to `<app>.exe.old`, copies the verified new binary into `<app>.exe` (with automatic rollback on failure), launches the new binary, and invokes the host app's `quitCallback()`. Stale `.old` files are cleaned up on subsequent launches via `UpdateInstaller::cleanupStaleBackup()`.

---

## 3. Android OTA Integration (`android/`)

### 3.1 Gradle Module Inclusion (`settings.gradle.kts`)

```kotlin
include(":selfupdate")
project(":selfupdate").projectDir = file("../../selfupdate/android")
```

### 3.2 App Dependency (`app/build.gradle.kts`)

```kotlin
dependencies {
    implementation(project(":selfupdate"))
}
```

### 3.3 Jetpack Compose UI Integration

```kotlin
val context = LocalContext.current
val controller = remember { SelfUpdateController(context) }
val updateState by controller.state.collectAsState()

LaunchedEffect(Unit) {
    controller.checkForUpdates()
}

SelfUpdateBanner(
    state = updateState,
    onDownloadClick = { controller.downloadAndInstall() },
    onDismiss = { controller.dismiss() }
)
```

---

## 4. Manifest Specifications (`version.json`)

The update architecture uses dual-schema JSON manifests supporting both master catalogs and single-app manifests.

### 4.1 Windows Manifest Schema (`https://www.selfso.com/software/windows/version.json`)

```json
{
  "schemaVersion": 1,
  "baseUrl": "https://www.selfso.com/software/windows/",
  "updatedAt": "2026-10-22T12:00:00Z",
  "apps": {
    "com.selfso.octi": {
      "slug": "octi",
      "title": "OCTI Desktop Player",
      "applicationId": "com.selfso.octi",
      "versionCode": 20003,
      "versionName": "2.0.3",
      "installType": "installer",
      "installerArgs": "/S",
      "executableName": "octi.exe",
      "arch": "x86_64",
      "minOs": "Windows 10 (64-bit)+",
      "packageUrl": "https://www.selfso.com/software/windows/octi/octi-setup.exe",
      "pageUrl": "https://www.selfso.com/software/windows/octi/",
      "sha256": "ec9f1da66a3ca38145225b765381ddd17a4cc2ae50db736dc07c9d5d52101ac0",
      "sizeBytes": 22458182,
      "publishedAt": "2026-10-22T12:00:00Z",
      "releaseNotes": "64-bit Windows Qt6 desktop client, minimax AI opponent & P2P voice lobby for OCTI."
    }
  }
}
```

---

## 5. Publishing CLI Tooling

### 5.1 Windows Application Publishing (`scripts/`)

- **`scripts/gen_windows_version_json.py`**: Parses PE header and traverses `.rsrc` table down to `RT_VERSION` (type ID 16) to extract machine architecture, `VS_FIXEDFILEINFO`, and `StringFileInfo` keys while remaining immune to embedded `RT_RCDATA` payloads. Emits single-app manifest JSON.
- **`scripts/publish_windows_app.py`**: Staged publisher for Windows applications. Non-destructively updates `~/work/www/selfso/html/software/windows/version.json`, stages packages, and renders static HTML portal pages.

```bash
# Publish a single Windows application from its build output:
python3 scripts/publish_windows_app.py --slug octi

# Batch-publish all known Windows applications across the workspace:
python3 scripts/publish_windows_app.py --publish-all
```

### 5.2 Android APK Publishing (`scripts/`)

- **`scripts/gen_version_json.py`**: Inspects Android `.apk` files using `aapt2` or AGP `output-metadata.json`.
- **`scripts/publish_android_apk.py`**: Stages APKs to `~/work/www/selfso/html/software/android/` and updates Android portal pages.

```bash
# Publish a single Android application:
python3 scripts/publish_android_apk.py --slug octi

# Batch-publish all known Android applications:
python3 scripts/publish_android_apk.py --publish-all
```

---

## 6. Build & Test Commands (`Makefile`)

```bash
# Run all unit tests (Python unittests, Android tests, C++ CppUTest + RapidCheck suites, and MinGW cross-compile check)
make test

# Run C++ suites with AddressSanitizer and UndefinedBehaviorSanitizer enabled
SANITIZE=1 make test

# Batch-publish all Android and Windows software
make publish-all

# Or publish individual platforms
make publish-android
make publish-windows
```
