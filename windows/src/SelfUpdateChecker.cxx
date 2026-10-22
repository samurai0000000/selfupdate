/*
 * SelfUpdateChecker.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/SelfUpdateChecker.hxx"
#include <stdexcept>
#include <vector>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace selfupdate {

SelfUpdateChecker::SelfUpdateChecker(const CheckerConfig& config,
                                     std::shared_ptr<HttpTransport> transport)
    : _config(config)
    , _transport(transport ? transport : HttpTransport::createDefault())
{
}

InstalledAppInfo SelfUpdateChecker::detectCurrentExeVersionInfo()
{
    InstalledAppInfo info;

#if defined(_WIN32)
    std::vector<wchar_t> exePath(MAX_PATH);
    DWORD len = GetModuleFileNameW(nullptr, exePath.data(), static_cast<DWORD>(exePath.size()));
    while (len == exePath.size() && GetLastError() == ERROR_INSUFFICIENT_BUFFER) {
        exePath.resize(exePath.size() * 2);
        len = GetModuleFileNameW(nullptr, exePath.data(), static_cast<DWORD>(exePath.size()));
    }
    if (len > 0) {
        int utf8Len = WideCharToMultiByte(CP_UTF8, 0, exePath.data(), len, nullptr, 0, nullptr, nullptr);
        if (utf8Len > 0) {
            std::vector<char> utf8Buf(utf8Len);
            WideCharToMultiByte(CP_UTF8, 0, exePath.data(), len, utf8Buf.data(), utf8Len, nullptr, nullptr);
            info.executablePath.assign(utf8Buf.data(), utf8Len);
        }

        DWORD verHandle = 0;
        DWORD verSize = GetFileVersionInfoSizeW(exePath.data(), &verHandle);
        if (verSize > 0) {
            std::vector<uint8_t> verData(verSize);
            if (GetFileVersionInfoW(exePath.data(), verHandle, verSize, verData.data())) {
                VS_FIXEDFILEINFO* fixedInfo = nullptr;
                UINT fixedLen = 0;
                if (VerQueryValueW(verData.data(), L"\\", reinterpret_cast<LPVOID*>(&fixedInfo), &fixedLen) && fixedInfo) {
                    uint32_t major = HIWORD(fixedInfo->dwProductVersionMS);
                    uint32_t minor = LOWORD(fixedInfo->dwProductVersionMS);
                    uint32_t patch = HIWORD(fixedInfo->dwProductVersionLS);
                    info.versionName = std::to_string(major) + "." + std::to_string(minor) + "." + std::to_string(patch);
                    info.versionCode = static_cast<int64_t>(major) * 10000 +
                                       static_cast<int64_t>(minor) * 100 +
                                       static_cast<int64_t>(patch);
                }

                struct Translation {
                    WORD language;
                    WORD codePage;
                } *trans = nullptr;
                UINT transLen = 0;
                if (VerQueryValueW(verData.data(), L"\\VarFileInfo\\Translation", reinterpret_cast<LPVOID*>(&trans), &transLen) && trans && transLen >= sizeof(Translation)) {
                    wchar_t subBlock[64];
                    swprintf(subBlock, sizeof(subBlock) / sizeof(wchar_t),
                             L"\\StringFileInfo\\%04x%04x\\ProductVersion",
                             trans[0].language, trans[0].codePage);
                    LPWSTR prodVer = nullptr;
                    UINT prodVerLen = 0;
                    if (VerQueryValueW(verData.data(), subBlock, reinterpret_cast<LPVOID*>(&prodVer), &prodVerLen) && prodVer && prodVerLen > 0) {
                        int pvLen = WideCharToMultiByte(CP_UTF8, 0, prodVer, -1, nullptr, 0, nullptr, nullptr);
                        if (pvLen > 0) {
                            std::vector<char> pvBuf(pvLen);
                            WideCharToMultiByte(CP_UTF8, 0, prodVer, -1, pvBuf.data(), pvLen, nullptr, nullptr);
                            info.versionName = pvBuf.data();
                        }
                    }

                    swprintf(subBlock, sizeof(subBlock) / sizeof(wchar_t),
                             L"\\StringFileInfo\\%04x%04x\\ProductName",
                             trans[0].language, trans[0].codePage);
                    LPWSTR prodName = nullptr;
                    UINT prodNameLen = 0;
                    if (VerQueryValueW(verData.data(), subBlock, reinterpret_cast<LPVOID*>(&prodName), &prodNameLen) && prodName && prodNameLen > 0) {
                        int pnLen = WideCharToMultiByte(CP_UTF8, 0, prodName, -1, nullptr, 0, nullptr, nullptr);
                        if (pnLen > 0) {
                            std::vector<char> pnBuf(pnLen);
                            WideCharToMultiByte(CP_UTF8, 0, prodName, -1, pnBuf.data(), pnLen, nullptr, nullptr);
                            info.applicationId = pnBuf.data();
                        }
                    }
                }
            }
        }
    }
#endif

    return info;
}

InstalledAppInfo SelfUpdateChecker::getInstalledAppInfo() const
{
    InstalledAppInfo info = detectCurrentExeVersionInfo();

    if (!_config.applicationId.empty()) {
        info.applicationId = _config.applicationId;
    }
    if (!_config.installedVersionName.empty()) {
        info.versionName = _config.installedVersionName;
    }
    if (_config.installedVersionCode > 0) {
        info.versionCode = _config.installedVersionCode;
    } else if (info.versionCode <= 0 && !info.versionName.empty()) {
        info.versionCode = UpdateManifest::parseVersionCode(info.versionName);
    }

    return info;
}

UpdateManifest SelfUpdateChecker::fetchManifest(const std::atomic<bool>* cancelFlag) const
{
    std::string targetUrl = UpdateManifest::normalizeManifestUrl(_config.manifestUrl);
    HttpResponse res = _transport->get(targetUrl, _config.connectTimeoutMs, _config.readTimeoutMs, cancelFlag);

    if (cancelFlag && cancelFlag->load()) {
        throw std::runtime_error("Manifest fetch cancelled");
    }
    if (!res.isSuccess()) {
        std::string err = "Failed to fetch update manifest from " + targetUrl;
        if (res.statusCode > 0) {
            err += ": HTTP " + std::to_string(res.statusCode);
        }
        if (!res.errorMessage.empty()) {
            err += " (" + res.errorMessage + ")";
        }
        throw std::runtime_error(err);
    }

    return UpdateManifest::fromJson(res.body, targetUrl, _config.applicationId);
}

UpdateState SelfUpdateChecker::checkForUpdate(bool isManualCheck,
                                              const std::atomic<bool>* cancelFlag) const
{
    UpdateState state;
    state.isManualCheck = isManualCheck;
    state.phase = UpdatePhase::Checking;

    InstalledAppInfo appInfo = getInstalledAppInfo();
    state.installedVersionName = appInfo.versionName;
    state.installedVersionCode = appInfo.versionCode;

    try {
        UpdateManifest manifest = fetchManifest(cancelFlag);
        state.manifest = manifest;
        if (manifest.isNewerThan(state.installedVersionName, state.installedVersionCode)) {
            state.phase = UpdatePhase::Available;
        } else {
            state.phase = UpdatePhase::UpToDate;
        }
    } catch (const std::exception& e) {
        state.phase = UpdatePhase::Error;
        state.errorMessage = e.what();
    }

    return state;
}

} // namespace selfupdate

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
