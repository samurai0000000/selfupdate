/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Downloads APK packages from the update server with progress reporting, cache hygiene,
 * and mandatory SHA-256 integrity verification.
 */
class ApkDownloader(
    private val cacheRootDir: File,
    private val connectTimeoutMs: Int = 15_000,
    private val readTimeoutMs: Int = 30_000
) {

    constructor(context: Context) : this(File(context.cacheDir, "selfupdate"))

    /**
     * Downloads the APK specified by [manifest], streams into a temporary `.part` file,
     * validates its SHA-256 checksum, and atomically stages it as `<appId>-<versionCode>.apk`.
     *
     * If an identical valid APK already exists in the cache directory, returns the cached file
     * immediately without performing redundant network transfers.
     */
    suspend fun downloadAndVerify(
        manifest: UpdateManifest,
        onProgress: (bytesRead: Long, totalBytes: Long) -> Unit = { _, _ -> }
    ): File = withContext(Dispatchers.IO) {
        if (!cacheRootDir.exists()) {
            cacheRootDir.mkdirs()
        }

        val targetFileName = "${manifest.applicationId}-${manifest.versionCode}.apk"
        val partFileName = "$targetFileName.part"
        val targetFile = File(cacheRootDir, targetFileName)
        val partFile = File(cacheRootDir, partFileName)

        // Cache hygiene: purge stale files from cache directory
        val existingFiles = cacheRootDir.listFiles()
        if (existingFiles != null) {
            for (file in existingFiles) {
                if (file.name != targetFileName) {
                    file.delete()
                }
            }
        }

        // Cache hit: check if the already downloaded target file has a valid SHA-256
        if (targetFile.exists() && targetFile.length() > 0L) {
            val existingSha256 = computeSha256(targetFile)
            if (existingSha256.equals(manifest.sha256.trim(), ignoreCase = true)) {
                onProgress(targetFile.length(), targetFile.length())
                return@withContext targetFile
            } else {
                targetFile.delete()
            }
        }

        val url = URL(manifest.apkUrl)
        val connection = url.openConnection() as HttpURLConnection
        val digest = MessageDigest.getInstance("SHA-256")
        var bytesRead = 0L

        try {
            connection.requestMethod = "GET"
            connection.instanceFollowRedirects = true
            connection.connectTimeout = connectTimeoutMs
            connection.readTimeout = readTimeoutMs

            val responseCode = connection.responseCode
            if (responseCode != HttpURLConnection.HTTP_OK) {
                throw IOException("HTTP $responseCode downloading APK from ${manifest.apkUrl}")
            }

            val contentLength = connection.contentLengthLong
            val totalBytes = if (contentLength > 0L) contentLength else manifest.sizeBytes

            connection.inputStream.use { input ->
                partFile.outputStream().use { output ->
                    val buffer = ByteArray(16 * 1024)
                    var read: Int
                    while (input.read(buffer).also { read = it } != -1) {
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                        bytesRead += read
                        onProgress(bytesRead, totalBytes)
                    }
                    output.flush()
                }
            }

            val computedSha256 = digest.digest().joinToString("") { "%02x".format(it) }
            val expectedSha256 = manifest.sha256.trim().lowercase()
            if (computedSha256 != expectedSha256) {
                if (partFile.exists()) {
                    partFile.delete()
                }
                throw SecurityException(
                    "SHA-256 mismatch: expected $expectedSha256, computed $computedSha256"
                )
            }

            if (!partFile.renameTo(targetFile)) {
                partFile.copyTo(targetFile, overwrite = true)
                partFile.delete()
            }

            targetFile
        } catch (t: Throwable) {
            if (partFile.exists()) {
                partFile.delete()
            }
            throw t
        } finally {
            connection.disconnect()
        }
    }

    private fun computeSha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(16 * 1024)
            var read: Int
            while (input.read(buffer).also { read = it } != -1) {
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
