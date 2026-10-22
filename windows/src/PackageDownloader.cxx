/*
 * PackageDownloader.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/PackageDownloader.hxx"
#include "selfupdate/Sha256.hxx"
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <vector>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace selfupdate {

namespace {

std::string toLower(const std::string& str)
{
    std::string out = str;
    for (char& c : out) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return out;
}

std::string sanitizeFilename(const std::string& rawUrl, const std::string& fallback)
{
    std::string s = rawUrl;
    size_t q = s.find('?');
    if (q != std::string::npos) {
        s = s.substr(0, q);
    }
    size_t h = s.find('#');
    if (h != std::string::npos) {
        s = s.substr(0, h);
    }
    size_t lastSlash = s.find_last_of("/\\");
    std::string filename = (lastSlash != std::string::npos) ? s.substr(lastSlash + 1) : s;

    // Filter dangerous characters
    std::string clean;
    for (char c : filename) {
        if (c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' ||
            c == '"' || c == '<' || c == '>' || c == '|' || c <= 31) {
            clean.push_back('_');
        } else {
            clean.push_back(c);
        }
    }
    while (clean.find("..") != std::string::npos) {
        clean.replace(clean.find(".."), 2, "_");
    }

    if (clean.empty() || clean == "." || clean == "..") {
        return fallback.empty() ? "package.exe" : (fallback + ".exe");
    }
    return clean;
}

} // namespace

PackageDownloader::PackageDownloader(const std::string& stagingDir,
                                     std::shared_ptr<HttpTransport> transport,
                                     int connectTimeoutMs,
                                     int readTimeoutMs)
    : _stagingDir(stagingDir)
    , _transport(transport ? transport : HttpTransport::createDefault())
    , _connectTimeoutMs(connectTimeoutMs)
    , _readTimeoutMs(readTimeoutMs)
{
}

std::string PackageDownloader::resolveStagingDir(const std::string& slug) const
{
    if (!_stagingDir.empty()) {
        return _stagingDir;
    }

    std::string effectiveSlug = slug.empty() ? "default" : slug;

#if defined(_WIN32)
    std::vector<wchar_t> tempPath(MAX_PATH);
    DWORD len = GetEnvironmentVariableW(L"TEMP", tempPath.data(), static_cast<DWORD>(tempPath.size()));
    if (len == 0) {
        len = GetEnvironmentVariableW(L"TMP", tempPath.data(), static_cast<DWORD>(tempPath.size()));
    }
    std::string baseTemp = "C:\\Windows\\Temp";
    if (len > 0) {
        int utf8Len = WideCharToMultiByte(CP_UTF8, 0, tempPath.data(), len, nullptr, 0, nullptr, nullptr);
        if (utf8Len > 0) {
            std::vector<char> utf8Buf(utf8Len);
            WideCharToMultiByte(CP_UTF8, 0, tempPath.data(), len, utf8Buf.data(), utf8Len, nullptr, nullptr);
            baseTemp.assign(utf8Buf.data(), utf8Len);
        }
    }
    std::filesystem::path p(baseTemp);
    p /= "selfupdate";
    p /= effectiveSlug;
    return p.string();
#else
    const char* tmpEnv = std::getenv("TMPDIR");
    std::string baseTemp = (tmpEnv && *tmpEnv) ? tmpEnv : "/tmp";
    std::filesystem::path p(baseTemp);
    p /= "selfupdate";
    p /= effectiveSlug;
    return p.string();
#endif
}

std::string PackageDownloader::downloadAndVerify(const UpdateManifest& manifest,
                                                 ProgressCallback onProgress,
                                                 const std::atomic<bool>* cancelFlag) const
{
    if (cancelFlag && cancelFlag->load()) {
        throw std::runtime_error("Download cancelled before start");
    }

    std::string slug = manifest.slug.empty() ? manifest.applicationId : manifest.slug;
    std::string stagingDir = resolveStagingDir(slug);

    std::error_code ec;
    std::filesystem::create_directories(stagingDir, ec);
    if (ec) {
        throw std::runtime_error("Failed to create staging directory '" + stagingDir + "': " + ec.message());
    }

    std::string filename = sanitizeFilename(manifest.packageUrl, slug);
    std::filesystem::path finalPath = std::filesystem::path(stagingDir) / filename;
    std::filesystem::path partPath = std::filesystem::path(stagingDir) / (filename + ".part");

    std::filesystem::remove(partPath, ec);

    std::ofstream out(partPath, std::ios::binary | std::ios::trunc);
    if (!out.is_open()) {
        throw std::runtime_error("Failed to open staging file for writing: " + partPath.string());
    }

    Sha256 hasher;
    int64_t bytesWritten = 0;
    std::string downloadError;

    bool ok = _transport->downloadStream(
        manifest.packageUrl,
        [&](const void* chunk, size_t chunkSize, int64_t totalBytes) -> bool {
            if (cancelFlag && cancelFlag->load()) {
                return false;
            }
            out.write(reinterpret_cast<const char*>(chunk), chunkSize);
            if (!out.good()) {
                return false;
            }
            hasher.update(chunk, chunkSize);
            bytesWritten += static_cast<int64_t>(chunkSize);
            if (onProgress) {
                int64_t effectiveTotal = totalBytes > 0 ? totalBytes : manifest.sizeBytes;
                onProgress(bytesWritten, effectiveTotal);
            }
            return true;
        },
        _connectTimeoutMs,
        _readTimeoutMs,
        cancelFlag,
        &downloadError);

    out.close();

    if (cancelFlag && cancelFlag->load()) {
        std::filesystem::remove(partPath, ec);
        throw std::runtime_error("Download cancelled");
    }

    if (!ok) {
        std::filesystem::remove(partPath, ec);
        throw std::runtime_error("Download failed: " + (downloadError.empty() ? "network transfer error" : downloadError));
    }

    if (manifest.sizeBytes > 0 && bytesWritten != manifest.sizeBytes) {
        std::filesystem::remove(partPath, ec);
        throw std::runtime_error("Package size mismatch: expected " + std::to_string(manifest.sizeBytes) +
                                 " bytes, received " + std::to_string(bytesWritten) + " bytes");
    }

    std::string computedSha = hasher.finalHex();
    if (toLower(computedSha) != toLower(manifest.sha256)) {
        std::filesystem::remove(partPath, ec);
        throw std::runtime_error("SHA-256 digest mismatch: expected " + manifest.sha256 +
                                 ", computed " + computedSha);
    }

    std::filesystem::remove(finalPath, ec);
    std::filesystem::rename(partPath, finalPath, ec);
    if (ec) {
        std::filesystem::remove(partPath, ec);
        throw std::runtime_error("Failed to rename temporary part file to target executable: " + ec.message());
    }

    return finalPath.string();
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
