/*
 * UpdateState.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_UPDATE_STATE_HXX
#define SELFUPDATE_UPDATE_STATE_HXX

#include <cstdint>
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
