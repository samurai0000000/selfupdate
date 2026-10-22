/*
 * TestDownloaderAndChecker.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include <rapidcheck.h>
#include <CppUTest/CommandLineTestRunner.h>
#include <CppUTest/TestHarness.h>
#include "selfupdate/PackageDownloader.hxx"
#include "selfupdate/SelfUpdateChecker.hxx"
#include "selfupdate/Sha256.hxx"
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <atomic>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <thread>
#include <vector>

using namespace selfupdate;

namespace {

class MockHttpServer {
public:
    MockHttpServer()
        : _serverSock(-1)
        , _port(0)
        , _stop(false)
    {
    }

    ~MockHttpServer()
    {
        stop();
    }

    void start()
    {
        _serverSock = socket(AF_INET, SOCK_STREAM, 0);
        int opt = 1;
        setsockopt(_serverSock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

        struct sockaddr_in addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        addr.sin_port = 0; // Bind to ephemeral port

        bind(_serverSock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr));
        listen(_serverSock, 16);

        socklen_t len = sizeof(addr);
        getsockname(_serverSock, reinterpret_cast<struct sockaddr*>(&addr), &len);
        _port = ntohs(addr.sin_port);

        _thread = std::thread([this]() { run(); });
    }

    void stop()
    {
        _stop = true;
        if (_serverSock >= 0) {
            shutdown(_serverSock, SHUT_RDWR);
            close(_serverSock);
            _serverSock = -1;
        }
        if (_thread.joinable()) {
            _thread.join();
        }
    }

    int port() const { return _port; }
    std::string baseUrl() const { return "http://127.0.0.1:" + std::to_string(_port); }

    void setPayload(const std::string& path, const std::string& body, const std::string& contentType = "application/octet-stream")
    {
        _routes[path] = {body, contentType, 200, ""};
    }

    void setRedirect(const std::string& path, const std::string& target)
    {
        _routes[path] = {"", "text/plain", 302, target};
    }

    void setError(const std::string& path, int status)
    {
        _routes[path] = {"Error", "text/plain", status, ""};
    }

private:
    struct Route {
        std::string body;
        std::string contentType;
        int status;
        std::string location;
    };

    void run()
    {
        while (!_stop) {
            if (_serverSock < 0) {
                break;
            }
            fd_set rfds;
            FD_ZERO(&rfds);
            FD_SET(_serverSock, &rfds);
            struct timeval tv;
            tv.tv_sec = 0;
            tv.tv_usec = 20000;
            int sel = select(_serverSock + 1, &rfds, nullptr, nullptr, &tv);
            if (sel <= 0) {
                continue;
            }

            struct sockaddr_in clientAddr;
            socklen_t clientLen = sizeof(clientAddr);
            int clientSock = accept(_serverSock, reinterpret_cast<struct sockaddr*>(&clientAddr), &clientLen);
            if (clientSock < 0) {
                if (_stop) break;
                continue;
            }

            char buf[4096];
            ssize_t n = recv(clientSock, buf, sizeof(buf) - 1, 0);
            if (n > 0) {
                buf[n] = '\0';
                std::istringstream req(buf);
                std::string method, path, proto;
                req >> method >> path >> proto;

                auto it = _routes.find(path);
                std::ostringstream resp;
                if (it != _routes.end()) {
                    if (it->second.status == 302) {
                        resp << "HTTP/1.1 302 Found\r\n";
                        resp << "Location: " << it->second.location << "\r\n";
                        resp << "Content-Length: 0\r\n";
                        resp << "Connection: close\r\n\r\n";
                    } else if (it->second.status == 200) {
                        resp << "HTTP/1.1 200 OK\r\n";
                        resp << "Content-Type: " << it->second.contentType << "\r\n";
                        resp << "Content-Length: " << it->second.body.size() << "\r\n";
                        resp << "Connection: close\r\n\r\n";
                        resp << it->second.body;
                    } else {
                        resp << "HTTP/1.1 " << it->second.status << " Error\r\n";
                        resp << "Content-Length: " << it->second.body.size() << "\r\n";
                        resp << "Connection: close\r\n\r\n";
                        resp << it->second.body;
                    }
                } else {
                    resp << "HTTP/1.1 404 Not Found\r\n";
                    resp << "Content-Length: 9\r\n";
                    resp << "Connection: close\r\n\r\n";
                    resp << "Not Found";
                }

                std::string respStr = resp.str();
                send(clientSock, respStr.data(), respStr.size(), 0);
            }
            close(clientSock);
        }
    }

    int _serverSock;
    int _port;
    std::atomic<bool> _stop;
    std::thread _thread;
    std::map<std::string, Route> _routes;
};

} // namespace

TEST_GROUP(DownloaderAndCheckerTests)
{
    MockHttpServer* server;
    std::string stagingDir;

    void setup() override
    {
        server = new MockHttpServer();
        server->start();

        stagingDir = "/tmp/test_selfupdate_stage_" + std::to_string(server->port());
        std::error_code ec;
        std::filesystem::remove_all(stagingDir, ec);
    }

    void teardown() override
    {
        server->stop();
        delete server;

        std::error_code ec;
        std::filesystem::remove_all(stagingDir, ec);
    }
};

TEST(DownloaderAndCheckerTests, CheckerAvailableAndUpToDate)
{
    std::string manifestJson = R"({
        "applicationId": "com.selfso.octi",
        "versionName": "2.0.3",
        "versionCode": 20003,
        "packageUrl": ")" + server->baseUrl() + R"(/octi-setup-2.0.3.exe",
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    })";

    server->setPayload("/version.json", manifestJson, "application/json");

    // Case 1: Installed app is older -> Available
    CheckerConfig config1;
    config1.applicationId = "com.selfso.octi";
    config1.installedVersionName = "2.0.2";
    config1.installedVersionCode = 20002;
    config1.manifestUrl = server->baseUrl() + "/version.json";

    SelfUpdateChecker checker1(config1);
    UpdateState state1 = checker1.checkForUpdate();
    CHECK(state1.phase == UpdatePhase::Available);
    CHECK_EQUAL("2.0.3", state1.manifest.versionName);
    CHECK_EQUAL(20003, state1.manifest.versionCode);

    // Case 2: Installed app is current -> UpToDate
    CheckerConfig config2;
    config2.applicationId = "com.selfso.octi";
    config2.installedVersionName = "2.0.3";
    config2.installedVersionCode = 20003;
    config2.manifestUrl = server->baseUrl() + "/version.json";

    SelfUpdateChecker checker2(config2);
    UpdateState state2 = checker2.checkForUpdate();
    CHECK(state2.phase == UpdatePhase::UpToDate);
}

TEST(DownloaderAndCheckerTests, CheckerRedirectAndErrorHandling)
{
    std::string manifestJson = R"({
        "applicationId": "com.selfso.octi",
        "versionName": "2.0.3",
        "versionCode": 20003,
        "packageUrl": "octi-setup-2.0.3.exe",
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    })";

    server->setPayload("/real_version.json", manifestJson, "application/json");
    server->setRedirect("/redirect_version.json", server->baseUrl() + "/real_version.json");
    server->setError("/server_error.json", 500);

    // Test Redirect
    CheckerConfig configRedir;
    configRedir.applicationId = "com.selfso.octi";
    configRedir.installedVersionName = "2.0.0";
    configRedir.manifestUrl = server->baseUrl() + "/redirect_version.json";
    SelfUpdateChecker checkerRedir(configRedir);
    UpdateState stateRedir = checkerRedir.checkForUpdate();
    CHECK(stateRedir.phase == UpdatePhase::Available);

    // Test HTTP 500 Error
    CheckerConfig configErr;
    configErr.applicationId = "com.selfso.octi";
    configErr.manifestUrl = server->baseUrl() + "/server_error.json";
    SelfUpdateChecker checkerErr(configErr);
    UpdateState stateErr = checkerErr.checkForUpdate();
    CHECK(stateErr.phase == UpdatePhase::Error);
    CHECK_FALSE(stateErr.errorMessage.empty());
}

TEST(DownloaderAndCheckerTests, DownloaderNominalAndProgress)
{
    std::string testPayload(4096, 'X');
    std::string testSha = Sha256::hashString(testPayload);

    server->setPayload("/files/octi-setup-2.0.3.exe", testPayload);

    UpdateManifest manifest;
    manifest.applicationId = "com.selfso.octi";
    manifest.slug = "octi";
    manifest.versionName = "2.0.3";
    manifest.versionCode = 20003;
    manifest.packageUrl = server->baseUrl() + "/files/octi-setup-2.0.3.exe";
    manifest.sha256 = testSha;
    manifest.sizeBytes = static_cast<int64_t>(testPayload.size());

    PackageDownloader downloader(stagingDir);

    int progressCalls = 0;
    int64_t lastBytesRead = 0;
    std::string finalPath = downloader.downloadAndVerify(
        manifest,
        [&](int64_t bytesRead, int64_t totalBytes) {
            progressCalls++;
            lastBytesRead = bytesRead;
            CHECK_EQUAL(static_cast<int64_t>(testPayload.size()), totalBytes);
        });

    CHECK(progressCalls > 0);
    CHECK_EQUAL(static_cast<int64_t>(testPayload.size()), lastBytesRead);
    CHECK_TRUE(std::filesystem::exists(finalPath));
    CHECK_FALSE(std::filesystem::exists(finalPath + ".part"));

    // Verify downloaded file content
    std::ifstream in(finalPath, std::ios::binary);
    std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    CHECK_EQUAL(testPayload, content);
}

TEST(DownloaderAndCheckerTests, DownloaderShaMismatchDeletesPart)
{
    std::string testPayload = "Valid payload from server";
    server->setPayload("/files/corrupt.exe", testPayload);

    UpdateManifest manifest;
    manifest.applicationId = "com.selfso.octi";
    manifest.slug = "octi";
    manifest.packageUrl = server->baseUrl() + "/files/corrupt.exe";
    manifest.sha256 = "0000000000000000000000000000000000000000000000000000000000000000";
    manifest.sizeBytes = static_cast<int64_t>(testPayload.size());

    PackageDownloader downloader(stagingDir);

    try {
        downloader.downloadAndVerify(manifest);
        FAIL("Expected SHA-256 mismatch exception");
    } catch (const std::runtime_error& e) {
        CHECK(std::string(e.what()).find("SHA-256 digest mismatch") != std::string::npos);
    }

    std::filesystem::path target = std::filesystem::path(stagingDir) / "corrupt.exe";
    CHECK_FALSE(std::filesystem::exists(target));
    CHECK_FALSE(std::filesystem::exists(target.string() + ".part"));
}

TEST(DownloaderAndCheckerTests, DownloaderSizeMismatchDeletesPart)
{
    std::string testPayload = "Short content";
    server->setPayload("/files/truncated.exe", testPayload);

    UpdateManifest manifest;
    manifest.applicationId = "com.selfso.octi";
    manifest.slug = "octi";
    manifest.packageUrl = server->baseUrl() + "/files/truncated.exe";
    manifest.sha256 = Sha256::hashString(testPayload);
    manifest.sizeBytes = 999999; // Expects much more

    PackageDownloader downloader(stagingDir);

    try {
        downloader.downloadAndVerify(manifest);
        FAIL("Expected size mismatch exception");
    } catch (const std::runtime_error& e) {
        CHECK(std::string(e.what()).find("Package size mismatch") != std::string::npos);
    }

    std::filesystem::path target = std::filesystem::path(stagingDir) / "truncated.exe";
    CHECK_FALSE(std::filesystem::exists(target));
    CHECK_FALSE(std::filesystem::exists(target.string() + ".part"));
}

TEST(DownloaderAndCheckerTests, DownloaderCancellationCleansUp)
{
    std::string testPayload(16384, 'C');
    server->setPayload("/files/cancel.exe", testPayload);

    UpdateManifest manifest;
    manifest.applicationId = "com.selfso.octi";
    manifest.slug = "octi";
    manifest.packageUrl = server->baseUrl() + "/files/cancel.exe";
    manifest.sha256 = Sha256::hashString(testPayload);
    manifest.sizeBytes = static_cast<int64_t>(testPayload.size());

    PackageDownloader downloader(stagingDir);
    std::atomic<bool> cancelFlag(false);

    try {
        downloader.downloadAndVerify(
            manifest,
            [&](int64_t /*bytesRead*/, int64_t /*totalBytes*/) {
                cancelFlag = true; // Trigger cancellation on first chunk
            },
            &cancelFlag);
        FAIL("Expected cancellation exception");
    } catch (const std::runtime_error& e) {
        CHECK(std::string(e.what()).find("cancelled") != std::string::npos);
    }

    std::filesystem::path target = std::filesystem::path(stagingDir) / "cancel.exe";
    CHECK_FALSE(std::filesystem::exists(target));
    CHECK_FALSE(std::filesystem::exists(target.string() + ".part"));
}

TEST(DownloaderAndCheckerTests, RapidCheckPropertyDownloadPayloadIntegrity)
{
    const bool prop = rc::check("Arbitrary payload download and verification integrity", [this]() {
        const auto payload = *rc::gen::container<std::string>(rc::gen::arbitrary<char>());
        const std::string sha = Sha256::hashString(payload);

        static int counter = 0;
        std::string path = "/files/rc_pkg_" + std::to_string(++counter) + ".bin";
        server->setPayload(path, payload);

        UpdateManifest m;
        m.applicationId = "com.selfso.rc";
        m.slug = "rc";
        m.packageUrl = server->baseUrl() + path;
        m.sha256 = sha;
        m.sizeBytes = static_cast<int64_t>(payload.size());

        PackageDownloader downloader(stagingDir);
        std::string downloaded = downloader.downloadAndVerify(m);

        std::ifstream in(downloaded, std::ios::binary);
        std::string content((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        RC_ASSERT(content == payload);

        std::error_code ec;
        std::filesystem::remove(downloaded, ec);
    });
    CHECK_TRUE(prop);
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
