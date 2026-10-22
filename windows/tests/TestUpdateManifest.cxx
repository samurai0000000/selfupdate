/*
 * TestUpdateManifest.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include <rapidcheck.h>
#include <CppUTest/CommandLineTestRunner.h>
#include <CppUTest/TestHarness.h>
#include "selfupdate/Sha256.hxx"
#include "selfupdate/UpdateManifest.hxx"
#include <algorithm>
#include <cctype>

using namespace selfupdate;

TEST_GROUP(UpdateManifestTests)
{
    void setup() override
    {
    }

    void teardown() override
    {
    }
};

TEST(UpdateManifestTests, NormalizeManifestUrl)
{
    CHECK_EQUAL("https://www.selfso.com/software/windows/version.json",
                UpdateManifest::normalizeManifestUrl(""));
    CHECK_EQUAL("https://www.selfso.com/software/windows/version.json",
                UpdateManifest::normalizeManifestUrl("   \t\n "));
    CHECK_EQUAL("https://www.selfso.com/software/windows/version.json",
                UpdateManifest::normalizeManifestUrl("https://www.selfso.com/software/windows/"));
    CHECK_EQUAL("https://www.selfso.com/software/windows/octi/version.json",
                UpdateManifest::normalizeManifestUrl("https://www.selfso.com/software/windows/octi/"));
    CHECK_EQUAL("https://www.selfso.com/software/windows/octi/version.json",
                UpdateManifest::normalizeManifestUrl("  https://www.selfso.com/software/windows/octi/version.json  "));
}

TEST(UpdateManifestTests, NormalizeApplicationId)
{
    CHECK_EQUAL("com.selfso.octi", UpdateManifest::normalizeApplicationId("com.selfso.octi"));
    CHECK_EQUAL("com.selfso.octi", UpdateManifest::normalizeApplicationId("com.selfso.octi.debug"));
    CHECK_EQUAL("com.selfso.octi", UpdateManifest::normalizeApplicationId("  com.selfso.octi.debug  "));
    CHECK_EQUAL("octi", UpdateManifest::normalizeApplicationId("octi"));
}

TEST(UpdateManifestTests, ResolveRelativeUrl)
{
    std::string base = "https://www.selfso.com/software/windows/version.json";

    CHECK_EQUAL("https://www.selfso.com/software/windows/octi/octi-setup-2.0.3.exe",
                UpdateManifest::resolveRelativeUrl(base, "octi/octi-setup-2.0.3.exe"));
    CHECK_EQUAL("https://www.selfso.com/downloads/package.exe",
                UpdateManifest::resolveRelativeUrl(base, "/downloads/package.exe"));
    CHECK_EQUAL("https://cdn.example.com/bin.exe",
                UpdateManifest::resolveRelativeUrl(base, "https://cdn.example.com/bin.exe"));
    CHECK_EQUAL("http://cdn.example.com/bin.exe",
                UpdateManifest::resolveRelativeUrl(base, "http://cdn.example.com/bin.exe"));
}

TEST(UpdateManifestTests, CompareVersions)
{
    CHECK(UpdateManifest::compareVersions("2.0.3", "2.0.2") > 0);
    CHECK(UpdateManifest::compareVersions("2.0.2", "2.0.3") < 0);
    CHECK_EQUAL(0, UpdateManifest::compareVersions("2.0.3", "2.0.3"));
    CHECK_EQUAL(0, UpdateManifest::compareVersions("v2.0.3", "2.0.3"));
    CHECK_EQUAL(0, UpdateManifest::compareVersions("V2.0.3", "2.0.3"));

    // Multi-digit component comparisons (1.10.0 vs 1.2.9)
    CHECK(UpdateManifest::compareVersions("1.10.0", "1.2.9") > 0);
    CHECK(UpdateManifest::compareVersions("1.2.9", "1.10.0") < 0);

    // Padding with zeros
    CHECK_EQUAL(0, UpdateManifest::compareVersions("2.0", "2.0.0"));
    CHECK_EQUAL(0, UpdateManifest::compareVersions("2", "2.0.0"));
    CHECK(UpdateManifest::compareVersions("2.1", "2.0.9") > 0);

    // Prerelease comparisons (release > prerelease)
    CHECK(UpdateManifest::compareVersions("2.0.0", "2.0.0-beta") > 0);
    CHECK(UpdateManifest::compareVersions("2.0.0-beta", "2.0.0-alpha") > 0);
    CHECK(UpdateManifest::compareVersions("2.0.0-alpha", "2.0.0-beta") < 0);
    CHECK_EQUAL(0, UpdateManifest::compareVersions("2.0.0-beta", "2.0.0-beta"));
}

TEST(UpdateManifestTests, ParseVersionCode)
{
    CHECK_EQUAL(20003, UpdateManifest::parseVersionCode("2.0.3"));
    CHECK_EQUAL(20003, UpdateManifest::parseVersionCode("v2.0.3"));
    CHECK_EQUAL(10203, UpdateManifest::parseVersionCode("1.2.3"));
    CHECK_EQUAL(11000, UpdateManifest::parseVersionCode("1.10.0"));
    CHECK_EQUAL(20000, UpdateManifest::parseVersionCode("2"));
    CHECK_EQUAL(20100, UpdateManifest::parseVersionCode("2.1"));
    CHECK_EQUAL(20000, UpdateManifest::parseVersionCode("2.0.0-beta1"));
}

TEST(UpdateManifestTests, IsNewerThan)
{
    UpdateManifest m;
    m.versionName = "2.0.3";
    m.versionCode = 20003;

    CHECK_TRUE(m.isNewerThan("2.0.2", 20002));
    CHECK_FALSE(m.isNewerThan("2.0.3", 20003));
    CHECK_FALSE(m.isNewerThan("2.0.4", 20004));

    // Equal versionName fallback to versionCode
    m.versionName = "2.0.3";
    m.versionCode = 20005;
    CHECK_TRUE(m.isNewerThan("2.0.3", 20003));
    CHECK_FALSE(m.isNewerThan("2.0.3", 20005));

    // Empty installedVersionName
    CHECK_TRUE(m.isNewerThan("", 20000));
    CHECK_FALSE(m.isNewerThan("", 30000));
}

TEST(UpdateManifestTests, Sha256StandardVectors)
{
    // RFC 6234 standard test vectors
    CHECK_EQUAL("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                Sha256::hashString(""));
    CHECK_EQUAL("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                Sha256::hashString("abc"));
    CHECK_EQUAL("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
                Sha256::hashString("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"));

    // Streaming updates
    Sha256 streamer;
    streamer.update("abc", 1);
    streamer.update("bc", 2);
    CHECK_EQUAL("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                streamer.finalHex());
}

TEST(UpdateManifestTests, ParseSingleAppManifest)
{
    const std::string json = R"({
        "applicationId": "com.selfso.octi",
        "versionName": "2.0.3",
        "versionCode": 20003,
        "installMode": "installer",
        "installerArgs": "/S",
        "executableName": "octi.exe",
        "arch": "x86_64",
        "minOs": "Windows 10 (64-bit)+",
        "packageUrl": "octi-setup-2.0.3.exe",
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "sizeBytes": 16482304,
        "slug": "octi",
        "title": "OCTI Desktop Player",
        "pageUrl": "index.html",
        "publishedAt": "2026-10-22T12:00:00Z",
        "releaseNotes": "Release 2.0.3 notes"
    })";

    UpdateManifest m = UpdateManifest::fromJson(json, "https://www.selfso.com/software/windows/octi/");
    CHECK_EQUAL("com.selfso.octi", m.applicationId);
    CHECK_EQUAL("2.0.3", m.versionName);
    CHECK_EQUAL(20003, m.versionCode);
    CHECK(m.installMode == InstallMode::Installer);
    CHECK_EQUAL("/S", m.installerArgs);
    CHECK_EQUAL("octi.exe", m.executableName);
    CHECK_EQUAL("x86_64", m.arch);
    CHECK_EQUAL("Windows 10 (64-bit)+", m.minOs);
    CHECK_EQUAL("https://www.selfso.com/software/windows/octi/octi-setup-2.0.3.exe", m.packageUrl);
    CHECK_EQUAL("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", m.sha256);
    CHECK_EQUAL(16482304, m.sizeBytes);
    CHECK_EQUAL("octi", m.slug);
    CHECK_EQUAL("OCTI Desktop Player", m.title);
    CHECK_EQUAL("https://www.selfso.com/software/windows/octi/index.html", m.pageUrl);
    CHECK_EQUAL("2026-10-22T12:00:00Z", m.publishedAt);
    CHECK_EQUAL("Release 2.0.3 notes", m.releaseNotes);
}

TEST(UpdateManifestTests, ParseBinaryCopyInstallMode)
{
    const std::string json = R"({
        "applicationId": "com.selfso.robohero.teleop",
        "versionName": "1.0.1",
        "versionCode": 10001,
        "installType": "binary",
        "packageUrl": "https://www.selfso.com/bin.exe",
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    })";

    UpdateManifest m = UpdateManifest::fromJson(json);
    CHECK(m.installMode == InstallMode::BinaryCopy);
    CHECK_EQUAL("x86_64", m.arch);
    CHECK_EQUAL("Windows 10 (64-bit)+", m.minOs);
}

TEST(UpdateManifestTests, ParseMasterCatalogLookup)
{
    const std::string json = R"({
        "schemaVersion": 1,
        "baseUrl": "https://www.selfso.com/software/windows/",
        "updatedAt": "2026-10-22T12:00:00Z",
        "apps": {
            "com.selfso.octi": {
                "slug": "octi",
                "title": "OCTI Desktop Player",
                "applicationId": "com.selfso.octi",
                "versionCode": 20003,
                "versionName": "2.0.3",
                "installType": "installer",
                "packageUrl": "octi/octi-setup-2.0.3.exe",
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
            },
            "com.selfso.aimon": {
                "slug": "aimon",
                "title": "AIMon System Tray",
                "applicationId": "com.selfso.aimon",
                "versionCode": 10203,
                "versionName": "1.2.3",
                "installType": "installer",
                "packageUrl": "aimon/aimon-setup-1.2.3.exe",
                "sha256": "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
            }
        }
    })";

    // Lookup by exact applicationId
    UpdateManifest octi = UpdateManifest::fromJson(json, "", "com.selfso.octi");
    CHECK_EQUAL("com.selfso.octi", octi.applicationId);
    CHECK_EQUAL("https://www.selfso.com/software/windows/octi/octi-setup-2.0.3.exe", octi.packageUrl);

    // Lookup by normalized applicationId (.debug)
    UpdateManifest octiDebug = UpdateManifest::fromJson(json, "", "com.selfso.octi.debug");
    CHECK_EQUAL("com.selfso.octi", octiDebug.applicationId);

    // Lookup by slug
    UpdateManifest aimon = UpdateManifest::fromJson(json, "", "aimon");
    CHECK_EQUAL("com.selfso.aimon", aimon.applicationId);
    CHECK_EQUAL("1.2.3", aimon.versionName);
    CHECK_EQUAL("https://www.selfso.com/software/windows/aimon/aimon-setup-1.2.3.exe", aimon.packageUrl);
}

TEST(UpdateManifestTests, CatalogSingleAppAutoSelection)
{
    const std::string json = R"({
        "apps": {
            "com.selfso.single": {
                "applicationId": "com.selfso.single",
                "versionName": "1.0.0",
                "versionCode": 10000,
                "packageUrl": "https://www.selfso.com/single.exe",
                "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
            }
        }
    })";

    UpdateManifest m = UpdateManifest::fromJson(json, "", "");
    CHECK_EQUAL("com.selfso.single", m.applicationId);
}

TEST(UpdateManifestTests, FaultHandlingInvalidInputs)
{
    // Invalid JSON syntax
    try {
        UpdateManifest::fromJson("{ invalid json }");
        FAIL("Expected std::invalid_argument on syntax error");
    } catch (const std::invalid_argument&) {}

    // Empty string
    try {
        UpdateManifest::fromJson("");
        FAIL("Expected std::invalid_argument on empty string");
    } catch (const std::invalid_argument&) {}

    // Non-object root
    try {
        UpdateManifest::fromJson("[1, 2, 3]");
        FAIL("Expected std::invalid_argument on non-object root");
    } catch (const std::invalid_argument&) {}

    // Missing applicationId
    try {
        UpdateManifest::fromJson(R"({
            "versionName": "1.0.0",
            "versionCode": 10000,
            "packageUrl": "https://example.com/app.exe",
            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        })");
        FAIL("Expected std::invalid_argument on missing applicationId");
    } catch (const std::invalid_argument&) {}

    // Invalid versionCode <= 0
    try {
        UpdateManifest::fromJson(R"({
            "applicationId": "com.selfso.test",
            "versionName": "1.0.0",
            "versionCode": 0,
            "packageUrl": "https://example.com/app.exe",
            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        })");
        FAIL("Expected std::invalid_argument on versionCode <= 0");
    } catch (const std::invalid_argument&) {}

    // Missing packageUrl
    try {
        UpdateManifest::fromJson(R"({
            "applicationId": "com.selfso.test",
            "versionName": "1.0.0",
            "versionCode": 10000,
            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        })");
        FAIL("Expected std::invalid_argument on missing packageUrl");
    } catch (const std::invalid_argument&) {}

    // Invalid sha256 (length != 64)
    try {
        UpdateManifest::fromJson(R"({
            "applicationId": "com.selfso.test",
            "versionName": "1.0.0",
            "versionCode": 10000,
            "packageUrl": "https://example.com/app.exe",
            "sha256": "1234abcd"
        })");
        FAIL("Expected std::invalid_argument on invalid sha256 length");
    } catch (const std::invalid_argument&) {}

    // Invalid sha256 (non-hex character)
    try {
        UpdateManifest::fromJson(R"({
            "applicationId": "com.selfso.test",
            "versionName": "1.0.0",
            "versionCode": 10000,
            "packageUrl": "https://example.com/app.exe",
            "sha256": "zz7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        })");
        FAIL("Expected std::invalid_argument on non-hex sha256");
    } catch (const std::invalid_argument&) {}

    // App not found in multi-app catalog
    try {
        UpdateManifest::fromJson(R"({
            "apps": {
                "com.selfso.octi": {
                    "applicationId": "com.selfso.octi",
                    "versionName": "1.0.0",
                    "versionCode": 10000,
                    "packageUrl": "https://example.com/app.exe",
                    "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
                }
            }
        })", "", "nonexistent_app");
        FAIL("Expected std::invalid_argument when app not in catalog");
    } catch (const std::invalid_argument&) {}
}

TEST(UpdateManifestTests, RapidCheckProperties)
{
    // Property 1: Version comparison reflexivity and antisymmetry on arbitrary numeric tuples
    const bool prop1 = rc::check("Version comparison reflexivity and antisymmetry", []() {
        const auto major1 = *rc::gen::inRange<int64_t>(0, 100);
        const auto minor1 = *rc::gen::inRange<int64_t>(0, 100);
        const auto patch1 = *rc::gen::inRange<int64_t>(0, 100);

        const auto major2 = *rc::gen::inRange<int64_t>(0, 100);
        const auto minor2 = *rc::gen::inRange<int64_t>(0, 100);
        const auto patch2 = *rc::gen::inRange<int64_t>(0, 100);

        std::string v1 = std::to_string(major1) + "." + std::to_string(minor1) + "." + std::to_string(patch1);
        std::string v2 = std::to_string(major2) + "." + std::to_string(minor2) + "." + std::to_string(patch2);

        RC_ASSERT(UpdateManifest::compareVersions(v1, v1) == 0);
        int c12 = UpdateManifest::compareVersions(v1, v2);
        int c21 = UpdateManifest::compareVersions(v2, v1);

        if (c12 > 0) {
            RC_ASSERT(c21 < 0);
        } else if (c12 < 0) {
            RC_ASSERT(c21 > 0);
        } else {
            RC_ASSERT(c21 == 0);
        }
    });
    CHECK_TRUE(prop1);

    // Property 2: SHA-256 streaming vs single-shot on arbitrary byte payloads
    const bool prop2 = rc::check("Sha256 arbitrary payload streaming vs single-shot", []() {
        const auto bytes = *rc::gen::container<std::vector<uint8_t>>(rc::gen::arbitrary<uint8_t>());
        std::string singleShot = Sha256::hashBytes(bytes.data(), bytes.size());
        RC_ASSERT(singleShot.size() == 64);
        for (char c : singleShot) {
            RC_ASSERT(std::isxdigit(static_cast<unsigned char>(c)));
            RC_ASSERT(!std::isupper(static_cast<unsigned char>(c)));
        }

        // Streaming in arbitrary chunk sizes
        Sha256 streamer;
        size_t offset = 0;
        while (offset < bytes.size()) {
            size_t chunkSize = 1 + (offset % 17);
            if (offset + chunkSize > bytes.size()) {
                chunkSize = bytes.size() - offset;
            }
            streamer.update(bytes.data() + offset, chunkSize);
            offset += chunkSize;
        }
        RC_ASSERT(streamer.finalHex() == singleShot);
    });
    CHECK_TRUE(prop2);

    // Property 3: Robustness on arbitrary random string inputs for fromJson
    const bool prop3 = rc::check("UpdateManifest::fromJson robustness against malformed inputs", []() {
        const auto randomInput = *rc::gen::arbitrary<std::string>();
        try {
            UpdateManifest::fromJson(randomInput);
        } catch (const std::invalid_argument&) {
            // Expected for malformed input
        } catch (const std::exception& e) {
            RC_FAIL(std::string("Unexpected exception type: ") + e.what());
        }
    });
    CHECK_TRUE(prop3);
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
