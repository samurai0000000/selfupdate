/*
 * SelfUpdateChecker.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_SELF_UPDATE_CHECKER_HXX
#define SELFUPDATE_SELF_UPDATE_CHECKER_HXX

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include "HttpTransport.hxx"
#include "UpdateManifest.hxx"
#include "UpdateState.hxx"

namespace selfupdate {

struct InstalledAppInfo {
    std::string applicationId;
    std::string versionName;
    int64_t versionCode = 0;
    std::string executablePath;
};

struct CheckerConfig {
    std::string applicationId;
    std::string installedVersionName;
    int64_t installedVersionCode = 0;
    std::string manifestUrl = UpdateManifest::DEFAULT_MANIFEST_URL;
    int connectTimeoutMs = 10000;
    int readTimeoutMs = 10000;
};

class SelfUpdateChecker {
public:
    explicit SelfUpdateChecker(const CheckerConfig& config,
                               std::shared_ptr<HttpTransport> transport = nullptr);

    InstalledAppInfo getInstalledAppInfo() const;
    UpdateManifest fetchManifest(const std::atomic<bool>* cancelFlag = nullptr) const;
    UpdateState checkForUpdate(bool isManualCheck = false,
                               const std::atomic<bool>* cancelFlag = nullptr) const;

    static InstalledAppInfo detectCurrentExeVersionInfo();

private:
    CheckerConfig _config;
    std::shared_ptr<HttpTransport> _transport;
};

} // namespace selfupdate

#endif // SELFUPDATE_SELF_UPDATE_CHECKER_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
