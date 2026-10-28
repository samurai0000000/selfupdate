/*
 * SelfUpdateController.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_SELF_UPDATE_CONTROLLER_HXX
#define SELFUPDATE_SELF_UPDATE_CONTROLLER_HXX

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include "HttpTransport.hxx"
#include "PackageDownloader.hxx"
#include "SelfUpdateChecker.hxx"
#include "UpdateInstaller.hxx"
#include "UpdateManifest.hxx"
#include "UpdateState.hxx"

namespace selfupdate {

class SelfUpdateController {
public:
    using StateCallback = std::function<void(const UpdateState&)>;
    using UiDispatcher = std::function<void(std::function<void()>)>;
    using QuitCallback = std::function<void()>;

    SelfUpdateController(const CheckerConfig& config,
                         const InstallOptions& installOptions = InstallOptions(),
                         const std::string& stagingDir = "",
                         std::shared_ptr<HttpTransport> transport = nullptr);
    ~SelfUpdateController();

    SelfUpdateController(const SelfUpdateController&) = delete;
    SelfUpdateController& operator=(const SelfUpdateController&) = delete;

    void setStateCallback(StateCallback callback);
    void setUiDispatcher(UiDispatcher dispatcher);
    void setQuitCallback(QuitCallback quitCallback);

    UpdateState state() const;
    InstallResult lastInstallResult() const;

    void checkForUpdates(bool isManualCheck = false);
    void downloadPackage(const UpdateManifest* manifestOverride = nullptr);
    void installStagedPackage();
    void downloadAndInstall(const UpdateManifest* manifestOverride = nullptr);
    void reinstall();
    void cancel();
    void dismiss();
    void waitForIdle();

private:
    void dispatchState(const UpdateState& state);
    void dispatchQuit();
    void stopWorker();

    mutable std::mutex _mutex;
    std::thread _workerThread;
    std::atomic<bool> _cancelFlag{false};

    CheckerConfig _config;
    InstallOptions _installOptions;
    std::string _stagingDir;
    std::shared_ptr<HttpTransport> _transport;

    SelfUpdateChecker _checker;
    PackageDownloader _downloader;
    UpdateInstaller _installer;

    UpdateState _state;
    InstallResult _lastInstallResult;

    StateCallback _stateCallback;
    UiDispatcher _uiDispatcher;
    QuitCallback _quitCallback;
};

} // namespace selfupdate

#endif // SELFUPDATE_SELF_UPDATE_CONTROLLER_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
