/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.pm.PackageInfoCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Checks for application updates against the remote selfupdate catalog.
 */
class SelfUpdateChecker(
    private val context: Context,
    val manifestUrl: String = UpdateManifest.DEFAULT_MANIFEST_URL,
    private val connectTimeoutMs: Int = 10_000,
    private val readTimeoutMs: Int = 10_000
) {

    data class InstalledPackageInfo(
        val applicationId: String,
        val versionCode: Long,
        val versionName: String
    )

    /**
     * Resolves the currently installed package's version code and version name.
     */
    fun getInstalledPackageInfo(): InstalledPackageInfo {
        val packageInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.packageManager.getPackageInfo(
                context.packageName,
                PackageManager.PackageInfoFlags.of(0)
            )
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.getPackageInfo(context.packageName, 0)
        }
        val versionCode = PackageInfoCompat.getLongVersionCode(packageInfo)
        val versionName = packageInfo.versionName ?: ""
        val applicationId = context.packageName
        return InstalledPackageInfo(applicationId, versionCode, versionName)
    }

    /**
     * Fetches and parses the remote [UpdateManifest] for the specified package ID.
     */
    suspend fun fetchManifest(targetApplicationId: String = context.packageName): UpdateManifest =
        withContext(Dispatchers.IO) {
            val normalizedUrl = UpdateManifest.normalizeManifestUrl(manifestUrl)
            val url = URL(normalizedUrl)
            val connection = url.openConnection() as HttpURLConnection
            try {
                connection.requestMethod = "GET"
                connection.connectTimeout = connectTimeoutMs
                connection.readTimeout = readTimeoutMs
                connection.setRequestProperty("Cache-Control", "no-cache")
                connection.setRequestProperty("Accept", "application/json")

                val responseCode = connection.responseCode
                if (responseCode != HttpURLConnection.HTTP_OK) {
                    throw IOException("HTTP $responseCode fetching manifest from $normalizedUrl")
                }

                val body = connection.inputStream.bufferedReader().use { it.readText() }
                UpdateManifest.fromJson(body, normalizedUrl, targetApplicationId)
            } finally {
                connection.disconnect()
            }
        }

    /**
     * Queries the update server and returns whether a newer version is available.
     */
    suspend fun checkForUpdate(): UpdateState {
        return try {
            val installed = getInstalledPackageInfo()
            val manifest = fetchManifest(installed.applicationId)
            if (manifest.isNewerThan(installed.versionCode)) {
                UpdateState.Available(
                    manifest = manifest,
                    installedVersionName = installed.versionName,
                    installedVersionCode = installed.versionCode
                )
            } else {
                UpdateState.UpToDate(
                    installedVersionName = installed.versionName,
                    installedVersionCode = installed.versionCode,
                    remoteManifest = manifest
                )
            }
        } catch (e: Exception) {
            UpdateState.Error(e.message ?: "Failed to check for updates")
        }
    }
}
