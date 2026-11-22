/*
 * UpdateState.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_UPDATE_STATE_HXX
#define SELFUPDATE_UPDATE_STATE_HXX

#include <cstdint>
#include <stdexcept>
#include <string>
#include "UpdateManifest.hxx"

namespace selfupdate {

enum class UpdatePhase {
    Idle,
    Checking,
    UpToDate,
    Available,
    Downloading,
    ReadyToInstall,
    Installing,
    Relaunching,
    Error
};

enum class UpdateErrorCode {
    None = 0,
    Cancelled,
    ManifestFetchFailed,
    ManifestParseFailed,
    NoPackageUrl,
    StagingFailed,
    DownloadFailed,
    SizeMismatch,
    Sha256Mismatch,
    NoStagedPackage,
    TargetExeNotFound,
    BinaryCopyFailed,
    InstallerLaunchFailed,
    Unknown
};

inline const char* updateErrorCodeToString(UpdateErrorCode code)
{
    switch (code) {
    case UpdateErrorCode::None:
        return "None";
    case UpdateErrorCode::Cancelled:
        return "Cancelled";
    case UpdateErrorCode::ManifestFetchFailed:
        return "ManifestFetchFailed";
    case UpdateErrorCode::ManifestParseFailed:
        return "ManifestParseFailed";
    case UpdateErrorCode::NoPackageUrl:
        return "NoPackageUrl";
    case UpdateErrorCode::StagingFailed:
        return "StagingFailed";
    case UpdateErrorCode::DownloadFailed:
        return "DownloadFailed";
    case UpdateErrorCode::SizeMismatch:
        return "SizeMismatch";
    case UpdateErrorCode::Sha256Mismatch:
        return "Sha256Mismatch";
    case UpdateErrorCode::NoStagedPackage:
        return "NoStagedPackage";
    case UpdateErrorCode::TargetExeNotFound:
        return "TargetExeNotFound";
    case UpdateErrorCode::BinaryCopyFailed:
        return "BinaryCopyFailed";
    case UpdateErrorCode::InstallerLaunchFailed:
        return "InstallerLaunchFailed";
    case UpdateErrorCode::Unknown:
    default:
        return "Unknown";
    }
}

class UpdateException : public std::runtime_error {
public:
    UpdateException(UpdateErrorCode code, const std::string& message)
        : std::runtime_error(message)
        , _code(code)
    {
    }

    UpdateErrorCode code() const noexcept
    {
        return _code;
    }

private:
    UpdateErrorCode _code;
};

inline const char* updatePhaseToString(UpdatePhase phase)
{
    switch (phase) {
    case UpdatePhase::Idle:
        return "Idle";
    case UpdatePhase::Checking:
        return "Checking";
    case UpdatePhase::UpToDate:
        return "UpToDate";
    case UpdatePhase::Available:
        return "Available";
    case UpdatePhase::Downloading:
        return "Downloading";
    case UpdatePhase::ReadyToInstall:
        return "ReadyToInstall";
    case UpdatePhase::Installing:
        return "Installing";
    case UpdatePhase::Relaunching:
        return "Relaunching";
    case UpdatePhase::Error:
        return "Error";
    default:
        return "Unknown";
    }
}

struct UpdateState {
    UpdatePhase phase = UpdatePhase::Idle;
    UpdateManifest manifest;
    std::string installedVersionName;
    int64_t installedVersionCode = 0;
    int64_t bytesRead = 0;
    int64_t totalBytes = -1;
    std::string stagedPackagePath;
    UpdateErrorCode errorCode = UpdateErrorCode::None;
    std::string errorMessage;
    bool isManualCheck = false;

    double progressFraction() const
    {
        if (totalBytes <= 0) {
            return -1.0;
        }
        if (bytesRead <= 0) {
            return 0.0;
        }
        if (bytesRead >= totalBytes) {
            return 1.0;
        }
        return static_cast<double>(bytesRead) / static_cast<double>(totalBytes);
    }
};

} // namespace selfupdate

#endif // SELFUPDATE_UPDATE_STATE_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
