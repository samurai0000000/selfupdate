/*
 * SelfUpdateController.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/SelfUpdateController.hxx"
#include <exception>

namespace selfupdate {

SelfUpdateController::SelfUpdateController(const CheckerConfig& config,
                                           const InstallOptions& installOptions,
                                           const std::string& stagingDir,
                                           std::shared_ptr<HttpTransport> transport)
    : _config(config)
    , _installOptions(installOptions)
    , _stagingDir(stagingDir)
    , _transport(transport ? transport : HttpTransport::createDefault())
    , _checker(_config, _transport)
    , _downloader(_stagingDir, _transport)
    , _installer(_installOptions)
{
    _state.installedVersionName = _config.installedVersionName;
    _state.installedVersionCode = _config.installedVersionCode;
    _state.phase = UpdatePhase::Idle;
}

SelfUpdateController::~SelfUpdateController()
{
    stopWorker();
}

void SelfUpdateController::setStateCallback(StateCallback callback)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _stateCallback = std::move(callback);
}

void SelfUpdateController::setUiDispatcher(UiDispatcher dispatcher)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _uiDispatcher = std::move(dispatcher);
}

void SelfUpdateController::setQuitCallback(QuitCallback quitCallback)
{
    std::lock_guard<std::mutex> lock(_mutex);
    _quitCallback = std::move(quitCallback);
}

UpdateState SelfUpdateController::state() const
{
    std::lock_guard<std::mutex> lock(_mutex);
    return _state;
}

InstallResult SelfUpdateController::lastInstallResult() const
{
    std::lock_guard<std::mutex> lock(_mutex);
    return _lastInstallResult;
}

void SelfUpdateController::checkForUpdates(bool isManualCheck)
{
    stopWorker();
    _cancelFlag.store(false);

    UpdateState checkingState;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        checkingState = _state;
        checkingState.phase = UpdatePhase::Checking;
        checkingState.isManualCheck = isManualCheck;
        checkingState.errorMessage.clear();
        _state = checkingState;
    }
    dispatchState(checkingState);

    _workerThread = std::thread([this, isManualCheck]() {
        UpdateState res = _checker.checkForUpdate(isManualCheck, &_cancelFlag);
        if (_cancelFlag.load()) {
            return;
        }
        dispatchState(res);
    });
}

void SelfUpdateController::downloadPackage(const UpdateManifest* manifestOverride)
{
    stopWorker();
    _cancelFlag.store(false);

    UpdateManifest manifest;
    UpdateState downloadingState;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        if (manifestOverride) {
            manifest = *manifestOverride;
        } else {
            manifest = _state.manifest;
        }
        downloadingState = _state;
        downloadingState.phase = UpdatePhase::Downloading;
        downloadingState.manifest = manifest;
        downloadingState.bytesRead = 0;
        downloadingState.totalBytes = manifest.sizeBytes;
        downloadingState.errorMessage.clear();
        _state = downloadingState;
    }

    if (manifest.packageUrl.empty()) {
        downloadingState.phase = UpdatePhase::Error;
        downloadingState.errorMessage = "No package URL to download";
        dispatchState(downloadingState);
        return;
    }

    dispatchState(downloadingState);

    _workerThread = std::thread([this, manifest]() {
        auto onProgress = [this, manifest](int64_t bytesRead, int64_t totalBytes) {
            if (_cancelFlag.load()) {
                return;
            }
            UpdateState st;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                st = _state;
                st.phase = UpdatePhase::Downloading;
                st.manifest = manifest;
                st.bytesRead = bytesRead;
                st.totalBytes = totalBytes;
            }
            dispatchState(st);
        };

        try {
            std::string staged = _downloader.downloadAndVerify(manifest, onProgress, &_cancelFlag);
            if (_cancelFlag.load()) {
                return;
            }
            UpdateState readyState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                readyState = _state;
                readyState.phase = UpdatePhase::ReadyToInstall;
                readyState.manifest = manifest;
                readyState.stagedPackagePath = staged;
                readyState.bytesRead = readyState.totalBytes > 0 ? readyState.totalBytes : manifest.sizeBytes;
                readyState.errorMessage.clear();
            }
            dispatchState(readyState);
        } catch (const std::exception& e) {
            if (_cancelFlag.load()) {
                return;
            }
            UpdateState errState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                errState = _state;
                errState.phase = UpdatePhase::Error;
                errState.errorMessage = e.what();
            }
            dispatchState(errState);
        }
    });
}

void SelfUpdateController::installStagedPackage()
{
    stopWorker();
    _cancelFlag.store(false);

    std::string staged;
    UpdateManifest manifest;
    UpdateState installingState;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        staged = _state.stagedPackagePath;
        manifest = _state.manifest;
        installingState = _state;
        installingState.phase = UpdatePhase::Installing;
        installingState.errorMessage.clear();
        _state = installingState;
    }

    if (staged.empty()) {
        installingState.phase = UpdatePhase::Error;
        installingState.errorMessage = "No staged package ready to install";
        dispatchState(installingState);
        return;
    }

    dispatchState(installingState);

    _workerThread = std::thread([this, manifest, staged]() {
        InstallResult res = _installer.executeUpdate(manifest, staged);
        {
            std::lock_guard<std::mutex> lock(_mutex);
            _lastInstallResult = res;
        }

        if (res.success) {
            UpdateState relaunchState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                relaunchState = _state;
                relaunchState.phase = UpdatePhase::Relaunching;
                relaunchState.errorMessage.clear();
            }
            dispatchState(relaunchState);

            if (res.requiresAppExit) {
                dispatchQuit();
            }
        } else {
            UpdateState errState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                errState = _state;
                errState.phase = UpdatePhase::Error;
                errState.errorMessage = res.errorMessage.empty() ? "Installation failed" : res.errorMessage;
            }
            dispatchState(errState);
        }
    });
}

void SelfUpdateController::downloadAndInstall(const UpdateManifest* manifestOverride)
{
    stopWorker();
    _cancelFlag.store(false);

    UpdateManifest manifest;
    UpdateState downloadingState;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        if (manifestOverride) {
            manifest = *manifestOverride;
        } else {
            manifest = _state.manifest;
        }
        downloadingState = _state;
        downloadingState.phase = UpdatePhase::Downloading;
        downloadingState.manifest = manifest;
        downloadingState.bytesRead = 0;
        downloadingState.totalBytes = manifest.sizeBytes;
        downloadingState.errorMessage.clear();
        _state = downloadingState;
    }

    if (manifest.packageUrl.empty()) {
        downloadingState.phase = UpdatePhase::Error;
        downloadingState.errorMessage = "No package URL to download";
        dispatchState(downloadingState);
        return;
    }

    dispatchState(downloadingState);

    _workerThread = std::thread([this, manifest]() {
        auto onProgress = [this, manifest](int64_t bytesRead, int64_t totalBytes) {
            if (_cancelFlag.load()) {
                return;
            }
            UpdateState st;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                st = _state;
                st.phase = UpdatePhase::Downloading;
                st.manifest = manifest;
                st.bytesRead = bytesRead;
                st.totalBytes = totalBytes;
            }
            dispatchState(st);
        };

        std::string staged;
        try {
            staged = _downloader.downloadAndVerify(manifest, onProgress, &_cancelFlag);
            if (_cancelFlag.load()) {
                return;
            }
            UpdateState readyState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                readyState = _state;
                readyState.phase = UpdatePhase::ReadyToInstall;
                readyState.manifest = manifest;
                readyState.stagedPackagePath = staged;
                readyState.bytesRead = readyState.totalBytes > 0 ? readyState.totalBytes : manifest.sizeBytes;
                readyState.errorMessage.clear();
            }
            dispatchState(readyState);
        } catch (const std::exception& e) {
            if (_cancelFlag.load()) {
                return;
            }
            UpdateState errState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                errState = _state;
                errState.phase = UpdatePhase::Error;
                errState.errorMessage = e.what();
            }
            dispatchState(errState);
            return;
        }

        UpdateState installingState;
        {
            std::lock_guard<std::mutex> lock(_mutex);
            installingState = _state;
            installingState.phase = UpdatePhase::Installing;
            installingState.errorMessage.clear();
            _state = installingState;
        }
        dispatchState(installingState);

        InstallResult res = _installer.executeUpdate(manifest, staged);
        {
            std::lock_guard<std::mutex> lock(_mutex);
            _lastInstallResult = res;
        }

        if (res.success) {
            UpdateState relaunchState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                relaunchState = _state;
                relaunchState.phase = UpdatePhase::Relaunching;
                relaunchState.errorMessage.clear();
            }
            dispatchState(relaunchState);

            if (res.requiresAppExit) {
                dispatchQuit();
            }
        } else {
            UpdateState errState;
            {
                std::lock_guard<std::mutex> lock(_mutex);
                errState = _state;
                errState.phase = UpdatePhase::Error;
                errState.errorMessage = res.errorMessage.empty() ? "Installation failed" : res.errorMessage;
            }
            dispatchState(errState);
        }
    });
}

void SelfUpdateController::cancel()
{
    _cancelFlag.store(true);
}

void SelfUpdateController::waitForIdle()
{
    if (_workerThread.joinable()) {
        if (_workerThread.get_id() != std::this_thread::get_id()) {
            _workerThread.join();
        }
    }
}

void SelfUpdateController::stopWorker()
{
    _cancelFlag.store(true);
    waitForIdle();
}

void SelfUpdateController::dismiss()
{
    stopWorker();
    UpdateState idleState;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        idleState.installedVersionName = _config.installedVersionName;
        idleState.installedVersionCode = _config.installedVersionCode;
        idleState.phase = UpdatePhase::Idle;
        _state = idleState;
    }
    dispatchState(idleState);
}

void SelfUpdateController::dispatchState(const UpdateState& state)
{
    StateCallback cb;
    UiDispatcher dispatcher;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        _state = state;
        cb = _stateCallback;
        dispatcher = _uiDispatcher;
    }
    if (cb) {
        if (dispatcher) {
            dispatcher([cb, state]() {
                cb(state);
            });
        } else {
            cb(state);
        }
    }
}

void SelfUpdateController::dispatchQuit()
{
    QuitCallback quit;
    UiDispatcher dispatcher;
    {
        std::lock_guard<std::mutex> lock(_mutex);
        quit = _quitCallback;
        dispatcher = _uiDispatcher;
    }
    if (quit) {
        if (dispatcher) {
            dispatcher([quit]() {
                quit();
            });
        } else {
            quit();
        }
    }
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
