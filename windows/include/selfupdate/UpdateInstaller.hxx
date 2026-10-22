/*
 * UpdateInstaller.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_UPDATE_INSTALLER_HXX
#define SELFUPDATE_UPDATE_INSTALLER_HXX

#include <string>
#include <vector>
#include "UpdateManifest.hxx"

namespace selfupdate {

struct InstallOptions {
    std::string currentExePath;           // Auto-detected via GetModuleFileNameW / /proc/self/exe if empty
    std::string targetExePath;            // Post-install executable to relaunch (defaults to currentExePath)
    std::string installerArgsOverride;    // If non-empty, overrides manifest.installerArgs
    std::vector<std::string> relaunchArgs;
    bool relaunchAfterInstall = true;
    bool waitForAppExitBeforeInstaller = true;
    bool dryRun = false;                  // Hermetic testing without spawning detached OS processes
};

struct InstallResult {
    bool success = false;
    bool requiresAppExit = false;
    std::string backupExePath;
    std::string trampolineScriptPath;
    std::string launchedCommand;
    std::string errorMessage;
};

class UpdateInstaller {
public:
    explicit UpdateInstaller(const InstallOptions& options = InstallOptions());

    const InstallOptions& options() const;

    static std::string detectCurrentExecutablePath();
    static bool cleanupStaleBackup(const std::string& exePath = "");

    InstallResult executeUpdate(const UpdateManifest& manifest,
                                const std::string& stagedPackagePath) const;
    InstallResult executeBinaryCopy(const std::string& stagedBinaryPath,
                                    const std::string& targetExePath = "") const;
    InstallResult executeSetupInstaller(const UpdateManifest& manifest,
                                        const std::string& stagedInstallerPath) const;

private:
    InstallOptions _options;
};

} // namespace selfupdate

#endif // SELFUPDATE_UPDATE_INSTALLER_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
