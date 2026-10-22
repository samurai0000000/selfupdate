/*
 * PackageDownloader.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_PACKAGE_DOWNLOADER_HXX
#define SELFUPDATE_PACKAGE_DOWNLOADER_HXX

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include "HttpTransport.hxx"
#include "UpdateManifest.hxx"

namespace selfupdate {

using ProgressCallback = std::function<void(int64_t bytesRead, int64_t totalBytes)>;

class PackageDownloader {
public:
    explicit PackageDownloader(const std::string& stagingDir = "",
                               std::shared_ptr<HttpTransport> transport = nullptr,
                               int connectTimeoutMs = 10000,
                               int readTimeoutMs = 30000);

    std::string downloadAndVerify(const UpdateManifest& manifest,
                                  ProgressCallback onProgress = nullptr,
                                  const std::atomic<bool>* cancelFlag = nullptr) const;

    std::string resolveStagingDir(const std::string& slug) const;

private:
    std::string _stagingDir;
    std::shared_ptr<HttpTransport> _transport;
    int _connectTimeoutMs;
    int _readTimeoutMs;
};

} // namespace selfupdate

#endif // SELFUPDATE_PACKAGE_DOWNLOADER_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
