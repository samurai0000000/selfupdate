/*
 * UpdateManifest.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_UPDATE_MANIFEST_HXX
#define SELFUPDATE_UPDATE_MANIFEST_HXX

#include <cstdint>
#include <string>

namespace selfupdate {

enum class InstallMode {
    Installer,
    BinaryCopy
};

struct UpdateManifest {
    std::string applicationId;
    int64_t versionCode = 0;
    std::string versionName;
    InstallMode installMode = InstallMode::Installer;
    std::string installerArgs;
    std::string executableName;
    std::string arch = "x86_64";
    std::string minOs = "Windows 10 (64-bit)+";
    std::string packageUrl;
    std::string sha256;
    int64_t sizeBytes = -1;
    std::string slug;
    std::string title;
    std::string pageUrl;
    std::string publishedAt;
    std::string releaseNotes;
    std::string latestPackageUrl;
    std::string latestSha256;
    int64_t latestSizeBytes = 0;
    std::string latestPublishedAt;

    static constexpr const char* DEFAULT_MANIFEST_URL =
        "https://www.selfso.com/software/windows/";

    bool isNewerThan(const std::string& installedVersionName,
                     int64_t installedVersionCode = 0) const;

    UpdateManifest reinstallManifest() const;

    static int compareVersions(const std::string& lhs, const std::string& rhs);
    static int64_t parseVersionCode(const std::string& versionName);
    static std::string normalizeManifestUrl(const std::string& url);
    static std::string normalizeApplicationId(const std::string& appId);
    static std::string resolveRelativeUrl(const std::string& baseUrl,
                                          const std::string& relativeOrAbsUrl);
    static UpdateManifest fromJson(const std::string& jsonString,
                                   const std::string& manifestUrl = DEFAULT_MANIFEST_URL,
                                   const std::string& targetIdOrSlug = "");
};

} // namespace selfupdate

#endif // SELFUPDATE_UPDATE_MANIFEST_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
