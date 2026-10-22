/*
 * TestWin32CrossCompile.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/HttpTransport.hxx"
#include "selfupdate/PackageDownloader.hxx"
#include "selfupdate/SelfUpdateChecker.hxx"
#include "selfupdate/SelfUpdateController.hxx"
#include "selfupdate/Sha256.hxx"
#include "selfupdate/UpdateInstaller.hxx"
#include "selfupdate/UpdateManifest.hxx"
#include "selfupdate/UpdateState.hxx"
#include <iostream>

int main(int argc, char* argv[])
{
    (void)argc;
    (void)argv;

    selfupdate::CheckerConfig config;
    config.applicationId = "com.selfso.smoke";
    config.installedVersionName = "1.0.0";
    config.installedVersionCode = 10000;
    config.manifestUrl = "https://www.selfso.com/software/windows/";

    selfupdate::InstallOptions installOpts;
    installOpts.dryRun = true;

    selfupdate::SelfUpdateChecker checker(config);
    selfupdate::InstalledAppInfo info = selfupdate::SelfUpdateChecker::detectCurrentExeVersionInfo();

    selfupdate::PackageDownloader downloader;
    selfupdate::UpdateInstaller installer(installOpts);
    selfupdate::SelfUpdateController controller(config, installOpts);

    std::string exePath = selfupdate::UpdateInstaller::detectCurrentExecutablePath();
    bool cleanup = selfupdate::UpdateInstaller::cleanupStaleBackup(exePath);

    selfupdate::UpdateManifest manifest;
    manifest.applicationId = "com.selfso.smoke";
    manifest.versionName = "1.0.1";
    manifest.versionCode = 10001;
    manifest.installMode = selfupdate::InstallMode::BinaryCopy;

    std::cout << "Win32 cross-compile smoke test initialized: " << exePath
              << " cleanup=" << cleanup << " detectedApp=" << info.applicationId
              << std::endl;

    if (argc > 1 && std::string(argv[1]) == "--live-check") {
        selfupdate::CheckerConfig liveCfg;
        liveCfg.applicationId = "com.selfso.octi";
        liveCfg.installedVersionName = "1.0.0";
        liveCfg.installedVersionCode = 10000;
        liveCfg.manifestUrl = "https://www.selfso.com/software/windows/";
        selfupdate::SelfUpdateChecker liveChecker(liveCfg);
        selfupdate::UpdateState state = liveChecker.checkForUpdate(true);
        if (state.phase != selfupdate::UpdatePhase::Available) {
            std::cerr << "LIVE CHECK FAILED: phase=" << selfupdate::updatePhaseToString(state.phase)
                      << " error=" << state.errorMessage << std::endl;
            return 1;
        }
        std::cout << "LIVE CHECK OK: fetched com.selfso.octi versionName="
                  << state.manifest.versionName << " versionCode=" << state.manifest.versionCode
                  << " packageUrl=" << state.manifest.packageUrl << std::endl;
    }
    return 0;
}

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
