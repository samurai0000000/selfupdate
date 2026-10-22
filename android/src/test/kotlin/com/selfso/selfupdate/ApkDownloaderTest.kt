/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpHandler
import com.sun.net.httpserver.HttpServer
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.nio.file.Files
import java.security.MessageDigest

class ApkDownloaderTest {

    private lateinit var server: HttpServer
    private lateinit var tempDir: File
    private var serverPort: Int = 0

    private var responseCodeToServe: Int = 200
    private var responseBytesToServe: ByteArray = ByteArray(0)

    @Before
    fun setUp() {
        tempDir = Files.createTempDirectory("selfupdate_test").toFile()
        server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        serverPort = server.address.port

        server.createContext("/test.apk", HttpHandler { exchange: HttpExchange ->
            if (responseCodeToServe == 200) {
                exchange.responseHeaders.set("Content-Type", "application/vnd.android.package-archive")
                exchange.sendResponseHeaders(200, responseBytesToServe.size.toLong())
                exchange.responseBody.use { it.write(responseBytesToServe) }
            } else {
                exchange.sendResponseHeaders(responseCodeToServe, -1)
            }
        })
        server.start()
    }

    @After
    fun tearDown() {
        server.stop(0)
        tempDir.deleteRecursively()
    }

    private fun sha256Hex(bytes: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256")
        return digest.digest(bytes).joinToString("") { "%02x".format(it) }
    }

    @Test
    fun testNominalDownloadAndVerify() = runBlocking {
        // Prepare 64 KB of test binary data
        responseBytesToServe = ByteArray(64 * 1024) { (it % 251).toByte() }
        responseCodeToServe = 200
        val expectedSha = sha256Hex(responseBytesToServe)

        val manifest = UpdateManifest(
            applicationId = "com.selfso.octi",
            versionCode = 20002L,
            versionName = "2.0.2",
            apkUrl = "http://127.0.0.1:$serverPort/test.apk",
            sha256 = expectedSha,
            sizeBytes = responseBytesToServe.size.toLong()
        )

        val progressReports = mutableListOf<Pair<Long, Long>>()
        val downloader = ApkDownloader(cacheRootDir = tempDir)

        val downloadedFile = downloader.downloadAndVerify(manifest) { bytesRead, totalBytes ->
            progressReports.add(bytesRead to totalBytes)
        }

        assertTrue(downloadedFile.exists())
        assertEquals("com.selfso.octi-20002.apk", downloadedFile.name)
        assertEquals(responseBytesToServe.size.toLong(), downloadedFile.length())
        assertEquals(expectedSha, sha256Hex(downloadedFile.readBytes()))

        // Verify progress callbacks
        assertTrue("Expected progress callbacks", progressReports.isNotEmpty())
        val lastReport = progressReports.last()
        assertEquals(responseBytesToServe.size.toLong(), lastReport.first)
        assertEquals(responseBytesToServe.size.toLong(), lastReport.second)

        // Monotonic check
        var prevBytes = 0L
        for (report in progressReports) {
            assertTrue("Progress must be monotonically increasing", report.first >= prevBytes)
            prevBytes = report.first
        }
    }

    @Test
    fun testCachedHitAndStaleFilesPurge() = runBlocking {
        // Place a pre-existing verified target file
        responseBytesToServe = ByteArray(32 * 1024) { (it % 127).toByte() }
        responseCodeToServe = 200
        val expectedSha = sha256Hex(responseBytesToServe)

        val targetFile = File(tempDir, "com.selfso.octi-20002.apk")
        targetFile.writeBytes(responseBytesToServe)

        // Place stale files that should be cleaned up
        val staleOldApk = File(tempDir, "com.selfso.octi-10001.apk")
        staleOldApk.writeBytes(ByteArray(100) { 1 })
        val stalePart = File(tempDir, "com.selfso.octi-20002.apk.part")
        stalePart.writeBytes(ByteArray(100) { 2 })

        assertTrue(staleOldApk.exists())
        assertTrue(stalePart.exists())

        val manifest = UpdateManifest(
            applicationId = "com.selfso.octi",
            versionCode = 20002L,
            versionName = "2.0.2",
            apkUrl = "http://127.0.0.1:$serverPort/test.apk",
            sha256 = expectedSha,
            sizeBytes = responseBytesToServe.size.toLong()
        )

        var progressReported = false
        val downloader = ApkDownloader(cacheRootDir = tempDir)
        val result = downloader.downloadAndVerify(manifest) { bytesRead, totalBytes ->
            assertEquals(targetFile.length(), bytesRead)
            assertEquals(targetFile.length(), totalBytes)
            progressReported = true
        }

        assertEquals(targetFile.absolutePath, result.absolutePath)
        assertTrue(progressReported)

        // Verify stale files were purged
        assertFalse("Stale old APK should be purged", staleOldApk.exists())
        assertFalse("Stale part file should be purged", stalePart.exists())
        assertTrue("Target file should be preserved", targetFile.exists())
    }

    @Test
    fun testFaultInjectionSha256Mismatch() = runBlocking {
        responseBytesToServe = "corrupted payload".toByteArray()
        responseCodeToServe = 200

        val manifest = UpdateManifest(
            applicationId = "com.selfso.octi",
            versionCode = 20002L,
            versionName = "2.0.2",
            apkUrl = "http://127.0.0.1:$serverPort/test.apk",
            sha256 = "0000000000000000000000000000000000000000000000000000000000000000",
            sizeBytes = responseBytesToServe.size.toLong()
        )

        val downloader = ApkDownloader(cacheRootDir = tempDir)
        try {
            downloader.downloadAndVerify(manifest)
            fail("Expected SecurityException on SHA-256 mismatch")
        } catch (e: SecurityException) {
            assertTrue(e.message?.contains("SHA-256 mismatch") == true)
        }

        // Verify .part file and .apk target file are not left behind
        val targetFile = File(tempDir, "com.selfso.octi-20002.apk")
        val partFile = File(tempDir, "com.selfso.octi-20002.apk.part")
        assertFalse("Target APK should not exist after failed verification", targetFile.exists())
        assertFalse("Temporary part file must be deleted after failed verification", partFile.exists())
    }

    @Test
    fun testFaultInjectionHttpErrors() = runBlocking {
        val errorCodes = listOf(404, 500)
        val downloader = ApkDownloader(cacheRootDir = tempDir)

        for (code in errorCodes) {
            responseCodeToServe = code
            val manifest = UpdateManifest(
                applicationId = "com.selfso.octi",
                versionCode = 20002L,
                versionName = "2.0.2",
                apkUrl = "http://127.0.0.1:$serverPort/test.apk",
                sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            )

            try {
                downloader.downloadAndVerify(manifest)
                fail("Expected IOException on HTTP $code")
            } catch (e: IOException) {
                assertTrue(e.message?.contains("HTTP $code") == true)
            }

            val targetFile = File(tempDir, "com.selfso.octi-20002.apk")
            val partFile = File(tempDir, "com.selfso.octi-20002.apk.part")
            assertFalse(targetFile.exists())
            assertFalse(partFile.exists())
        }
    }
}
