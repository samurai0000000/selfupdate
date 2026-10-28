/*
 * TestInstallerAndController.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#if defined(SELFUPDATE_HAVE_QT)
#include <QCoreApplication>
#include <QObject>
#include "selfupdate/QtSelfUpdateBridge.hxx"
#endif

#include <rapidcheck.h>
#include <CppUTest/CommandLineTestRunner.h>
#include <CppUTest/TestHarness.h>
#include "selfupdate/HttpTransport.hxx"
#include "selfupdate/PackageDownloader.hxx"
#include "selfupdate/SelfUpdateChecker.hxx"
#include "selfupdate/SelfUpdateController.hxx"
#include "selfupdate/Sha256.hxx"
#include "selfupdate/UpdateInstaller.hxx"
#include "selfupdate/UpdateManifest.hxx"
#include "selfupdate/UpdateState.hxx"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using namespace selfupdate;

namespace {

class MockTransport : public HttpTransport {
public:
    std::string manifestJson;
    std::string packageBytes;
    int getStatus = 200;
    int downloadStatus = 200;

    HttpResponse get(const std::string& url,
                     int connectTimeoutMs = 10000,
                     int readTimeoutMs = 10000,
                     const std::atomic<bool>* cancelFlag = nullptr) override
    {
        (void)url;
        (void)connectTimeoutMs;
        (void)readTimeoutMs;
        if (cancelFlag && cancelFlag->load()) {
            HttpResponse r;
            r.statusCode = 0;
            r.errorMessage = "Cancelled";
            return r;
        }
        HttpResponse resp;
        resp.statusCode = getStatus;
        resp.body = manifestJson;
        return resp;
    }

    bool downloadStream(const std::string& url,
                        StreamChunkCallback onChunk,
                        int connectTimeoutMs = 10000,
                        int readTimeoutMs = 30000,
                        const std::atomic<bool>* cancelFlag = nullptr,
                        std::string* outError = nullptr) override
    {
        (void)url;
        (void)connectTimeoutMs;
        (void)readTimeoutMs;
        if (cancelFlag && cancelFlag->load()) {
            if (outError) {
                *outError = "Download cancelled";
            }
            return false;
        }
        if (downloadStatus != 200) {
            if (outError) {
                *outError = "HTTP status " + std::to_string(downloadStatus);
            }
            return false;
        }

        if (onChunk) {
            size_t chunkSize = 1024;
            for (size_t offset = 0; offset < packageBytes.size(); offset += chunkSize) {
                if (cancelFlag && cancelFlag->load()) {
                    if (outError) {
                        *outError = "Download cancelled mid-stream";
                    }
                    return false;
                }
                size_t n = std::min(chunkSize, packageBytes.size() - offset);
                if (!onChunk(packageBytes.data() + offset, n, static_cast<int64_t>(packageBytes.size()))) {
                    return false;
                }
            }
        }
        return true;
    }
};

std::string createSandboxDir(const std::string& prefix)
{
    std::filesystem::path p = std::filesystem::temp_directory_path() /
        (prefix + "_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count()));
    std::filesystem::create_directories(p);
    return p.string();
}

void writeFile(const std::string& path, const std::string& content)
{
    std::ofstream out(path, std::ios::out | std::ios::binary | std::ios::trunc);
    out << content;
    out.close();
}

std::string readFile(const std::string& path)
{
    std::ifstream in(path, std::ios::in | std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

} // namespace

TEST_GROUP(UpdateInstallerTest) {
    std::string sandbox;

    void setup() override
    {
        sandbox = createSandboxDir("test_installer");
    }

    void teardown() override
    {
        std::error_code ec;
        std::filesystem::remove_all(sandbox, ec);
    }
};

TEST(UpdateInstallerTest, DetectCurrentExecutablePath)
{
    std::string path = UpdateInstaller::detectCurrentExecutablePath();
    CHECK_FALSE(path.empty());
    std::error_code ec;
    CHECK_TRUE(std::filesystem::exists(path, ec));
}

TEST(UpdateInstallerTest, CleanupStaleBackup)
{
    std::string testExe = sandbox + "/app.exe";
    std::string testOld = testExe + ".old";

    // Non-existent .old returns true
    CHECK_TRUE(UpdateInstaller::cleanupStaleBackup(testExe));

    // Create .old and verify cleanup removes it
    writeFile(testOld, "previous binary backup");
    std::error_code ec;
    CHECK_TRUE(std::filesystem::exists(testOld, ec));

    CHECK_TRUE(UpdateInstaller::cleanupStaleBackup(testExe));
    CHECK_FALSE(std::filesystem::exists(testOld, ec));
}

TEST(UpdateInstallerTest, ExecuteBinaryCopy_MissingStaged)
{
    InstallOptions opts;
    opts.dryRun = true;
    UpdateInstaller installer(opts);

    InstallResult res = installer.executeBinaryCopy(sandbox + "/nonexistent.bin", sandbox + "/app.exe");
    CHECK_FALSE(res.success);
    CHECK_FALSE(res.errorMessage.empty());
}

TEST(UpdateInstallerTest, ExecuteBinaryCopy_SuccessAndRelaunch)
{
    std::string targetExe = sandbox + "/myapp.exe";
    std::string stagedBinary = sandbox + "/staged.exe";

    writeFile(targetExe, "original v1.0.0");
    std::filesystem::permissions(targetExe,
                                 std::filesystem::perms::owner_all |
                                 std::filesystem::perms::group_read | std::filesystem::perms::group_exec |
                                 std::filesystem::perms::others_read | std::filesystem::perms::others_exec);

    writeFile(stagedBinary, "upgraded v2.0.0");

    InstallOptions opts;
    opts.targetExePath = targetExe;
    opts.relaunchAfterInstall = true;
    opts.relaunchArgs = {"--upgraded", "1"};
    opts.dryRun = true;

    UpdateInstaller installer(opts);
    InstallResult res = installer.executeBinaryCopy(stagedBinary);

    CHECK_TRUE(res.success);
    CHECK_TRUE(res.requiresAppExit);
    CHECK_EQUAL(targetExe + ".old", res.backupExePath);
    CHECK_TRUE(res.launchedCommand.find(targetExe) != std::string::npos);
    CHECK_TRUE(res.launchedCommand.find("--upgraded") != std::string::npos);

    // Verify file contents
    CHECK_EQUAL("upgraded v2.0.0", readFile(targetExe));
    CHECK_EQUAL("original v1.0.0", readFile(targetExe + ".old"));

    // Cleanup stale backup removes .old
    CHECK_TRUE(UpdateInstaller::cleanupStaleBackup(targetExe));
    std::error_code ec;
    CHECK_FALSE(std::filesystem::exists(targetExe + ".old", ec));
}

TEST(UpdateInstallerTest, ExecuteBinaryCopy_RollbackOnFailure)
{
    std::string targetExe = sandbox + "/rollback_app.exe";
    std::string stagedBinary = sandbox + "/unreadable_staged.exe";

    writeFile(targetExe, "stable v1.0.0");
    std::filesystem::permissions(targetExe, std::filesystem::perms::owner_all);

    writeFile(stagedBinary, "corrupt payload");
    // Make staged file completely unreadable so copy fails
    std::filesystem::permissions(stagedBinary, std::filesystem::perms::none);

    InstallOptions opts;
    opts.targetExePath = targetExe;
    opts.relaunchAfterInstall = false;
    opts.dryRun = true;

    UpdateInstaller installer(opts);
    InstallResult res = installer.executeBinaryCopy(stagedBinary);

    CHECK_FALSE(res.success);
    CHECK_TRUE(res.errorMessage.find("restored backup") != std::string::npos);

    // Target executable must be restored to original content!
    CHECK_EQUAL("stable v1.0.0", readFile(targetExe));

    // Restore permissions for cleanup
    std::filesystem::permissions(stagedBinary, std::filesystem::perms::owner_all);
}

TEST(UpdateInstallerTest, ExecuteSetupInstaller_TrampolineGeneration)
{
    std::string stagedInstaller = sandbox + "/installer.exe";
    writeFile(stagedInstaller, "dummy installer binary");

    UpdateManifest manifest;
    manifest.applicationId = "com.selfso.octi";
    manifest.installerArgs = "/S";
    manifest.installMode = InstallMode::Installer;

    InstallOptions opts;
    opts.waitForAppExitBeforeInstaller = true;
    opts.relaunchAfterInstall = true;
    opts.targetExePath = sandbox + "/octi.exe";
    opts.relaunchArgs = {"--minimized"};
    opts.dryRun = true;

    UpdateInstaller installer(opts);
    InstallResult res = installer.executeSetupInstaller(manifest, stagedInstaller);

    CHECK_TRUE(res.success);
    CHECK_TRUE(res.requiresAppExit);
    CHECK_FALSE(res.trampolineScriptPath.empty());

    std::error_code ec;
    CHECK_TRUE(std::filesystem::exists(res.trampolineScriptPath, ec));

    std::string scriptContent = readFile(res.trampolineScriptPath);
    CHECK_TRUE(scriptContent.find("installer.exe") != std::string::npos);
    CHECK_TRUE(scriptContent.find("/S") != std::string::npos);
    CHECK_TRUE(scriptContent.find("octi.exe") != std::string::npos);
    CHECK_TRUE(scriptContent.find("--minimized") != std::string::npos);
}

TEST(UpdateInstallerTest, ExecuteUpdate_DispatchesCorrectly)
{
    std::string targetExe = sandbox + "/dispatch_app.exe";
    std::string stagedPkg = sandbox + "/package.bin";
    writeFile(targetExe, "old v1");
    writeFile(stagedPkg, "new v2");

    InstallOptions opts;
    opts.targetExePath = targetExe;
    opts.dryRun = true;
    UpdateInstaller installer(opts);

    // BinaryCopy mode
    UpdateManifest binManifest;
    binManifest.installMode = InstallMode::BinaryCopy;
    InstallResult binRes = installer.executeUpdate(binManifest, stagedPkg);
    CHECK_TRUE(binRes.success);
    CHECK_EQUAL("new v2", readFile(targetExe));

    // Installer mode
    UpdateManifest instManifest;
    instManifest.installMode = InstallMode::Installer;
    instManifest.installerArgs = "/silent";
    InstallResult instRes = installer.executeUpdate(instManifest, stagedPkg);
    CHECK_TRUE(instRes.success);
    CHECK_FALSE(instRes.trampolineScriptPath.empty());
}

TEST_GROUP(SelfUpdateControllerTest) {
    std::string sandbox;
    std::string stagingDir;
    std::string installedDir;
    std::shared_ptr<MockTransport> transport;
    CheckerConfig config;
    InstallOptions installOpts;

    void setup() override
    {
        sandbox = createSandboxDir("test_controller");
        stagingDir = sandbox + "/staging";
        installedDir = sandbox + "/installed";
        std::filesystem::create_directories(stagingDir);
        std::filesystem::create_directories(installedDir);

        transport = std::make_shared<MockTransport>();

        config.applicationId = "com.selfso.octi";
        config.installedVersionName = "2.0.2";
        config.installedVersionCode = 20002;
        config.manifestUrl = "http://mock.local/version.json";

        installOpts.dryRun = true;
        installOpts.targetExePath = installedDir + "/octi.exe";
        writeFile(installOpts.targetExePath, "octi v2.0.2 executable");
    }

    void teardown() override
    {
        std::error_code ec;
        std::filesystem::remove_all(sandbox, ec);
    }
};

TEST(SelfUpdateControllerTest, InitialStateAndDismiss)
{
    SelfUpdateController controller(config, installOpts, stagingDir, transport);
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Idle), static_cast<int>(controller.state().phase));
    CHECK_EQUAL("2.0.2", controller.state().installedVersionName);
    CHECK_EQUAL(20002, controller.state().installedVersionCode);

    controller.dismiss();
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Idle), static_cast<int>(controller.state().phase));
}

TEST(SelfUpdateControllerTest, CheckForUpdates_Available_ManualFlag)
{
    std::string json = R"({
        "schemaVersion": 1,
        "apps": {
            "com.selfso.octi": {
                "applicationId": "com.selfso.octi",
                "versionName": "2.0.3",
                "versionCode": 20003,
                "packageUrl": "http://mock.local/octi-setup-2.0.3.exe",
                "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
                "sizeBytes": 1024
            }
        }
    })";
    transport->manifestJson = json;

    SelfUpdateController controller(config, installOpts, stagingDir, transport);

    std::vector<UpdatePhase> phases;
    controller.setStateCallback([&phases](const UpdateState& st) {
        phases.push_back(st.phase);
    });

    controller.checkForUpdates(true);
    controller.waitForIdle();

    UpdateState st = controller.state();
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Available), static_cast<int>(st.phase));
    CHECK_TRUE(st.isManualCheck);
    CHECK_EQUAL("2.0.3", st.manifest.versionName);
    CHECK_EQUAL(20003, st.manifest.versionCode);
    CHECK_TRUE(phases.size() >= 2);
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Checking), static_cast<int>(phases[0]));
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Available), static_cast<int>(phases.back()));
}

TEST(SelfUpdateControllerTest, CheckForUpdates_UpToDate)
{
    std::string json = R"({
        "applicationId": "com.selfso.octi",
        "versionName": "2.0.2",
        "versionCode": 20002,
        "packageUrl": "http://mock.local/octi.exe",
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    })";
    transport->manifestJson = json;

    SelfUpdateController controller(config, installOpts, stagingDir, transport);
    controller.checkForUpdates(false);
    controller.waitForIdle();

    UpdateState st = controller.state();
    CHECK_EQUAL_TEXT(static_cast<int>(UpdatePhase::UpToDate), static_cast<int>(st.phase), st.errorMessage.c_str());
    CHECK_FALSE(st.isManualCheck);
}

TEST(SelfUpdateControllerTest, DownloadAndInstall_EndToEnd)
{
    std::string pkgPayload = "verified binary payload 2.0.3";
    std::string sha = Sha256::hashString(pkgPayload);

    std::string json = "{\n"
                       "  \"applicationId\": \"com.selfso.octi\",\n"
                       "  \"versionName\": \"2.0.3\",\n"
                       "  \"versionCode\": 20003,\n"
                       "  \"installType\": \"binary\",\n"
                       "  \"packageUrl\": \"http://mock.local/octi.exe\",\n"
                       "  \"sha256\": \"" + sha + "\",\n"
                       "  \"sizeBytes\": " + std::to_string(pkgPayload.size()) + "\n"
                       "}";
    transport->manifestJson = json;
    transport->packageBytes = pkgPayload;

    SelfUpdateController controller(config, installOpts, stagingDir, transport);

    std::vector<UpdatePhase> phases;
    bool quitCalled = false;

    controller.setStateCallback([&phases](const UpdateState& st) {
        phases.push_back(st.phase);
    });

    controller.setQuitCallback([&quitCalled]() {
        quitCalled = true;
    });

    controller.checkForUpdates(true);
    controller.waitForIdle();
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Available), static_cast<int>(controller.state().phase));

    controller.downloadAndInstall();
    controller.waitForIdle();

    UpdateState finalSt = controller.state();
    CHECK_EQUAL_TEXT(static_cast<int>(UpdatePhase::Relaunching), static_cast<int>(finalSt.phase), finalSt.errorMessage.c_str());
    CHECK_TRUE(quitCalled);
    CHECK_TRUE(controller.lastInstallResult().success);
    CHECK_EQUAL(pkgPayload, readFile(installOpts.targetExePath));
}

TEST(SelfUpdateControllerTest, Reinstall_PullsLatestBuild)
{
    std::string publicPayload = "public binary payload 2.0.2";
    std::string publicSha = Sha256::hashString(publicPayload);

    std::string latestPayload = "developer iteration binary payload 2.0.2 latest";
    std::string latestSha = Sha256::hashString(latestPayload);

    std::string json = "{\n"
                       "  \"applicationId\": \"com.selfso.octi\",\n"
                       "  \"versionName\": \"2.0.2\",\n"
                       "  \"versionCode\": 20002,\n"
                       "  \"installType\": \"binary\",\n"
                       "  \"packageUrl\": \"http://mock.local/octi.exe\",\n"
                       "  \"sha256\": \"" + publicSha + "\",\n"
                       "  \"sizeBytes\": " + std::to_string(publicPayload.size()) + ",\n"
                       "  \"latest\": {\n"
                       "    \"packageFilename\": \"octi-latest.exe\",\n"
                       "    \"packageUrl\": \"http://mock.local/octi-latest.exe\",\n"
                       "    \"sha256\": \"" + latestSha + "\",\n"
                       "    \"sizeBytes\": " + std::to_string(latestPayload.size()) + "\n"
                       "  }\n"
                       "}";
    transport->manifestJson = json;
    transport->packageBytes = latestPayload;

    SelfUpdateController controller(config, installOpts, stagingDir, transport);

    std::vector<UpdatePhase> phases;
    bool quitCalled = false;

    controller.setStateCallback([&phases](const UpdateState& st) {
        phases.push_back(st.phase);
    });

    controller.setQuitCallback([&quitCalled]() {
        quitCalled = true;
    });

    controller.checkForUpdates(true);
    controller.waitForIdle();
    CHECK_EQUAL(static_cast<int>(UpdatePhase::UpToDate), static_cast<int>(controller.state().phase));

    controller.reinstall();
    controller.waitForIdle();

    UpdateState finalSt = controller.state();
    CHECK_EQUAL_TEXT(static_cast<int>(UpdatePhase::Relaunching), static_cast<int>(finalSt.phase), finalSt.errorMessage.c_str());
    CHECK_TRUE(quitCalled);
    CHECK_TRUE(controller.lastInstallResult().success);
    CHECK_EQUAL(latestPayload, readFile(installOpts.targetExePath));
}

TEST(SelfUpdateControllerTest, Download_CorruptSha256_TransitionsToError)
{
    std::string pkgPayload = "valid payload";
    std::string json = "{\n"
                       "  \"applicationId\": \"com.selfso.octi\",\n"
                       "  \"versionName\": \"2.0.3\",\n"
                       "  \"versionCode\": 20003,\n"
                       "  \"packageUrl\": \"http://mock.local/octi.exe\",\n"
                       "  \"sha256\": \"0000000000000000000000000000000000000000000000000000000000000000\",\n"
                       "  \"sizeBytes\": " + std::to_string(pkgPayload.size()) + "\n"
                       "}";
    transport->manifestJson = json;
    transport->packageBytes = pkgPayload;

    SelfUpdateController controller(config, installOpts, stagingDir, transport);
    controller.checkForUpdates(false);
    controller.waitForIdle();

    controller.downloadPackage();
    controller.waitForIdle();

    UpdateState st = controller.state();
    CHECK_EQUAL(static_cast<int>(UpdatePhase::Error), static_cast<int>(st.phase));
    CHECK_FALSE(st.errorMessage.empty());
}

TEST(SelfUpdateControllerTest, RapidDestruction_NoDeadlock)
{
    transport->manifestJson = "{}";
    {
        SelfUpdateController controller(config, installOpts, stagingDir, transport);
        controller.checkForUpdates(true);
        // Destructor joins worker thread cleanly without deadlock or hang
    }
    CHECK_TRUE(true);
}

#if defined(SELFUPDATE_HAVE_QT)

TEST_GROUP(QtSelfUpdateBridgeTest) {
    std::string sandbox;
    std::string stagingDir;
    std::string installedDir;
    std::shared_ptr<MockTransport> transport;
    CheckerConfig config;
    InstallOptions installOpts;

    void setup() override
    {
        sandbox = createSandboxDir("test_qt_bridge");
        stagingDir = sandbox + "/staging";
        installedDir = sandbox + "/installed";
        std::filesystem::create_directories(stagingDir);
        std::filesystem::create_directories(installedDir);
        transport = std::make_shared<MockTransport>();

        config.applicationId = "com.selfso.octi";
        config.installedVersionName = "2.0.2";
        config.installedVersionCode = 20002;
        config.manifestUrl = "http://mock.local/version.json";

        installOpts.dryRun = true;
        installOpts.targetExePath = installedDir + "/octi.exe";
        writeFile(installOpts.targetExePath, "octi binary");
    }

    void teardown() override
    {
        std::error_code ec;
        std::filesystem::remove_all(sandbox, ec);
    }
};

TEST(QtSelfUpdateBridgeTest, EventLoopThreadDelivery)
{
    int argc = 1;
    char arg0[] = "test_selfupdate";
    char* argv[] = {arg0, nullptr};
    QCoreApplication app(argc, argv);

    std::string json = R"({
        "applicationId": "com.selfso.octi",
        "versionName": "2.0.3",
        "versionCode": 20003,
        "packageUrl": "http://mock.local/octi.exe",
        "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    })";
    transport->manifestJson = json;

    SelfUpdateController controller(config, installOpts, stagingDir, transport);
    QObject receiver;

    std::thread::id mainThreadId = std::this_thread::get_id();
    std::thread::id callbackThreadId;
    std::vector<UpdatePhase> phases;
    bool quitReceived = false;

    bindQtController(controller, &receiver,
        [&](const UpdateState& st) {
            callbackThreadId = std::this_thread::get_id();
            phases.push_back(st.phase);
        },
        [&]() {
            quitReceived = true;
        });

    controller.checkForUpdates(true);

    // Pump Qt event loop until update check completes
    auto start = std::chrono::steady_clock::now();
    while (phases.empty() || phases.back() == UpdatePhase::Checking) {
        app.processEvents(QEventLoop::AllEvents, 50);
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        if (std::chrono::steady_clock::now() - start > std::chrono::seconds(5)) {
            break;
        }
    }

    controller.waitForIdle();
    app.processEvents(QEventLoop::AllEvents, 50);

    CHECK_EQUAL(static_cast<int>(UpdatePhase::Available), static_cast<int>(controller.state().phase));
    CHECK_TRUE(callbackThreadId == mainThreadId);
    CHECK_TRUE(phases.size() >= 2);
}

#endif // SELFUPDATE_HAVE_QT

TEST_GROUP(RapidCheckProperties) {
};

TEST(RapidCheckProperties, CleanupStaleBackupIdempotence)
{
    bool allPassed = rc::check("cleanupStaleBackup is idempotent", []() {
        std::string sbox = createSandboxDir("rc_cleanup");
        std::string baseExe = sbox + "/test.exe";
        std::string oldExe = baseExe + ".old";

        writeFile(oldExe, "backup");
        bool removed = UpdateInstaller::cleanupStaleBackup(baseExe);
        RC_ASSERT(removed);

        std::error_code ec;
        RC_ASSERT(!std::filesystem::exists(oldExe, ec));

        // Second cleanup call is idempotent and returns true
        bool second = UpdateInstaller::cleanupStaleBackup(baseExe);
        RC_ASSERT(second);

        std::filesystem::remove_all(sbox, ec);
    });

    CHECK_TRUE(allPassed);
}

TEST(RapidCheckProperties, TrampolineScriptGeneratesValidArgs)
{
    bool allPassed = rc::check("Trampoline generation embeds args", [](const std::string& argToken) {
        RC_PRE(!argToken.empty());
        RC_PRE(argToken.find('\0') == std::string::npos);
        RC_PRE(argToken.find('\r') == std::string::npos);
        RC_PRE(argToken.find('\n') == std::string::npos);

        std::string sbox = createSandboxDir("rc_trampoline");
        std::string installer = sbox + "/inst.exe";
        writeFile(installer, "installer");

        UpdateManifest manifest;
        manifest.installMode = InstallMode::Installer;
        manifest.installerArgs = argToken;

        InstallOptions opts;
        opts.dryRun = true;
        opts.waitForAppExitBeforeInstaller = true;
        UpdateInstaller inst(opts);

        InstallResult res = inst.executeSetupInstaller(manifest, installer);
        RC_ASSERT(res.success);
        RC_ASSERT(!res.trampolineScriptPath.empty());

        std::string content = readFile(res.trampolineScriptPath);
        RC_ASSERT(content.find(argToken) != std::string::npos);

        std::error_code ec;
        std::filesystem::remove_all(sbox, ec);
    });

    CHECK_TRUE(allPassed);
}

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
