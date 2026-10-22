/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import org.json.JSONException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class UpdateManifestTest {

    private val masterCatalogJson = """
        {
          "schemaVersion": 1,
          "baseUrl": "https://www.selfso.com/software/android/",
          "updatedAt": "2026-10-22T09:15:00Z",
          "apps": {
            "com.selfso.octi": {
              "slug": "octi",
              "title": "OCTI Strategy Game",
              "applicationId": "com.selfso.octi",
              "versionCode": 20002,
              "versionName": "2.0.2",
              "minSdk": 24,
              "targetSdk": 35,
              "apkUrl": "octi/octi.apk",
              "pageUrl": "https://www.selfso.com/software/android/octi/",
              "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
              "sizeBytes": 5412890,
              "publishedAt": "2026-10-22T09:15:00Z",
              "releaseNotes": "OCTI abstract strategy board game."
            },
            "com.selfso.robohero": {
              "slug": "robohero",
              "title": "RoboHero Controller",
              "applicationId": "com.selfso.robohero",
              "versionCode": 10001,
              "versionName": "1.0.1",
              "minSdk": 24,
              "targetSdk": 35,
              "apkUrl": "https://www.selfso.com/software/android/robohero/robohero.apk",
              "pageUrl": "https://www.selfso.com/software/android/robohero/",
              "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
              "sizeBytes": 8192000,
              "publishedAt": "2026-10-22T09:15:00Z",
              "releaseNotes": "RoboHero motion controller."
            },
            "com.selfso.nigosh": {
              "slug": "nigosh",
              "title": "Nigosh Companion",
              "applicationId": "com.selfso.nigosh",
              "versionCode": 10003,
              "versionName": "1.0.3",
              "minSdk": 24,
              "targetSdk": 35,
              "apkUrl": "nigosh/nigosh.apk",
              "pageUrl": "https://www.selfso.com/software/android/nigosh/",
              "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
              "sizeBytes": 6123456,
              "publishedAt": "2026-10-22T09:15:00Z",
              "releaseNotes": "Nigosh companion app."
            },
            "dev.saifmukhtar.antimatter": {
              "slug": "antimatter",
              "title": "Antimatter AI",
              "applicationId": "dev.saifmukhtar.antimatter",
              "versionCode": 30005,
              "versionName": "3.0.5",
              "minSdk": 26,
              "targetSdk": 35,
              "apkUrl": "antimatter/antimatter.apk",
              "pageUrl": "https://www.selfso.com/software/android/antimatter/",
              "sha256": "3333333333333333333333333333333333333333333333333333333333333333",
              "sizeBytes": 9876543,
              "publishedAt": "2026-10-22T09:15:00Z",
              "releaseNotes": "Antimatter mobile client."
            }
          }
        }
    """.trimIndent()

    @Test
    fun testParseMasterCatalogAllApps() {
        val baseUrl = "https://www.selfso.com/software/android/"

        // 1. OCTI
        val octi = UpdateManifest.fromJson(masterCatalogJson, baseUrl, "com.selfso.octi")
        assertEquals("com.selfso.octi", octi.applicationId)
        assertEquals(20002L, octi.versionCode)
        assertEquals("2.0.2", octi.versionName)
        assertEquals("https://www.selfso.com/software/android/octi/octi.apk", octi.apkUrl)
        assertEquals("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", octi.sha256)
        assertEquals(5412890L, octi.sizeBytes)
        assertEquals("octi", octi.slug)
        assertEquals("OCTI Strategy Game", octi.title)

        // 2. RoboHero
        val robohero = UpdateManifest.fromJson(masterCatalogJson, baseUrl, "com.selfso.robohero")
        assertEquals("com.selfso.robohero", robohero.applicationId)
        assertEquals(10001L, robohero.versionCode)
        assertEquals("1.0.1", robohero.versionName)
        assertEquals("https://www.selfso.com/software/android/robohero/robohero.apk", robohero.apkUrl)

        // 3. Nigosh
        val nigosh = UpdateManifest.fromJson(masterCatalogJson, baseUrl, "com.selfso.nigosh")
        assertEquals("com.selfso.nigosh", nigosh.applicationId)
        assertEquals(10003L, nigosh.versionCode)
        assertEquals("1.0.3", nigosh.versionName)
        assertEquals("https://www.selfso.com/software/android/nigosh/nigosh.apk", nigosh.apkUrl)

        // 4. Antimatter
        val antimatter = UpdateManifest.fromJson(masterCatalogJson, baseUrl, "dev.saifmukhtar.antimatter")
        assertEquals("dev.saifmukhtar.antimatter", antimatter.applicationId)
        assertEquals(30005L, antimatter.versionCode)
        assertEquals("3.0.5", antimatter.versionName)
        assertEquals("https://www.selfso.com/software/android/antimatter/antimatter.apk", antimatter.apkUrl)
    }

    @Test
    fun testDebugSuffixStripping() {
        val baseUrl = "https://www.selfso.com/software/android/"

        // Target with .debug suffix finds app in catalog
        val antimatterDebug = UpdateManifest.fromJson(
            masterCatalogJson,
            baseUrl,
            "dev.saifmukhtar.antimatter.debug"
        )
        assertEquals("dev.saifmukhtar.antimatter", antimatterDebug.applicationId)
        assertEquals(30005L, antimatterDebug.versionCode)

        // Target with .debug suffix parses single-app JSON with base applicationId
        val singleAppJson = """
            {
              "applicationId": "dev.saifmukhtar.antimatter",
              "versionCode": 30006,
              "versionName": "3.0.6",
              "apkUrl": "https://www.selfso.com/software/android/antimatter/antimatter.apk",
              "sha256": "4444444444444444444444444444444444444444444444444444444444444444"
            }
        """.trimIndent()
        val parsed = UpdateManifest.fromJson(
            singleAppJson,
            baseUrl,
            "dev.saifmukhtar.antimatter.debug"
        )
        assertEquals("dev.saifmukhtar.antimatter", parsed.applicationId)
        assertEquals(30006L, parsed.versionCode)
    }

    @Test
    fun testUrlNormalization() {
        assertEquals(
            "https://www.selfso.com/software/android/version.json",
            UpdateManifest.normalizeManifestUrl("https://www.selfso.com/software/android/")
        )
        assertEquals(
            "https://www.selfso.com/software/android/version.json",
            UpdateManifest.normalizeManifestUrl("")
        )
        assertEquals(
            "https://www.selfso.com/software/android/version.json",
            UpdateManifest.normalizeManifestUrl("   ")
        )
        assertEquals(
            "https://example.com/software/version.json",
            UpdateManifest.normalizeManifestUrl("https://example.com/software/version.json")
        )
        assertEquals(
            "https://example.com/custom/version.json",
            UpdateManifest.normalizeManifestUrl("  https://example.com/custom/  ")
        )
    }

    @Test
    fun testRelativeApkUrlResolution() {
        val json = """
            {
              "applicationId": "com.selfso.octi",
              "versionCode": 10,
              "versionName": "1.0",
              "apkUrl": "octi.apk",
              "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            }
        """.trimIndent()

        val manifest = UpdateManifest.fromJson(
            json,
            "https://www.selfso.com/software/android/octi/version.json"
        )
        assertEquals(
            "https://www.selfso.com/software/android/octi/octi.apk",
            manifest.apkUrl
        )
    }

    @Test
    fun testIsNewerThanBoundaries() {
        val manifest = UpdateManifest(
            applicationId = "com.selfso.octi",
            versionCode = 200L,
            versionName = "2.0.0",
            apkUrl = "https://www.selfso.com/software/android/octi/octi.apk",
            sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        assertTrue(manifest.isNewerThan(199L))
        assertFalse(manifest.isNewerThan(200L))
        assertFalse(manifest.isNewerThan(201L))
    }

    @Test
    fun testFaultInjectionUnknownAppInCatalog() {
        try {
            UpdateManifest.fromJson(
                masterCatalogJson,
                "https://www.selfso.com/software/android/",
                "com.nonexistent.app"
            )
            fail("Expected IllegalArgumentException for unknown app")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message?.contains("not found in master update catalog") == true)
        }
    }

    @Test
    fun testFaultInjectionPackageIdMismatch() {
        val singleAppJson = """
            {
              "applicationId": "com.selfso.octi",
              "versionCode": 20002,
              "versionName": "2.0.2",
              "apkUrl": "https://www.selfso.com/software/android/octi/octi.apk",
              "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            }
        """.trimIndent()

        try {
            UpdateManifest.fromJson(
                singleAppJson,
                "https://www.selfso.com/software/android/octi/version.json",
                "com.selfso.robohero"
            )
            fail("Expected IllegalArgumentException for package ID mismatch")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message?.contains("Package ID mismatch") == true)
        }
    }

    @Test
    fun testFaultInjectionInvalidSha256() {
        val invalidShaCases = listOf(
            "12345", // too short
            "g".repeat(64), // invalid hex char
            "0".repeat(65) // too long
        )

        for (badSha in invalidShaCases) {
            val json = """
                {
                  "applicationId": "com.selfso.octi",
                  "versionCode": 1,
                  "versionName": "1.0",
                  "apkUrl": "https://www.selfso.com/software/android/octi/octi.apk",
                  "sha256": "$badSha"
                }
            """.trimIndent()

            try {
                UpdateManifest.fromJson(json)
                fail("Expected IllegalArgumentException for bad SHA-256: $badSha")
            } catch (e: IllegalArgumentException) {
                assertTrue(e.message?.contains("Invalid sha256 checksum") == true)
            }
        }
    }

    @Test
    fun testFaultInjectionNonPositiveVersionCode() {
        val badVersionCodes = listOf(0L, -1L, -100L)
        for (vc in badVersionCodes) {
            val json = """
                {
                  "applicationId": "com.selfso.octi",
                  "versionCode": $vc,
                  "versionName": "1.0",
                  "apkUrl": "https://www.selfso.com/software/android/octi/octi.apk",
                  "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                }
            """.trimIndent()

            try {
                UpdateManifest.fromJson(json)
                fail("Expected IllegalArgumentException for versionCode: $vc")
            } catch (e: IllegalArgumentException) {
                assertTrue(e.message?.contains("versionCode must be greater than 0") == true)
            }
        }
    }

    @Test
    fun testFaultInjectionMalformedJson() {
        try {
            UpdateManifest.fromJson("{ not valid json }")
            fail("Expected JSONException for malformed JSON")
        } catch (e: JSONException) {
            // Success
        }
    }
}
