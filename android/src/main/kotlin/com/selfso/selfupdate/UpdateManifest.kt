/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import org.json.JSONObject
import java.net.URI

/**
 * Metadata describing an available application release on the update server.
 */
data class UpdateManifest(
    val applicationId: String,
    val versionCode: Long,
    val versionName: String,
    val apkUrl: String,
    val sha256: String,
    val sizeBytes: Long = -1L,
    val minSdk: Int = 24,
    val targetSdk: Int = 35,
    val slug: String = "",
    val title: String = "",
    val pageUrl: String = "",
    val publishedAt: String = "",
    val releaseNotes: String = ""
) {

    /**
     * Returns true if this manifest's [versionCode] is strictly greater than [installedVersionCode].
     */
    fun isNewerThan(installedVersionCode: Long): Boolean = versionCode > installedVersionCode

    companion object {
        const val DEFAULT_MANIFEST_URL = "https://www.selfso.com/software/android/"

        private val SHA256_HEX_REGEX = Regex("^[0-9a-f]{64}$")

        /**
         * Normalizes a manifest URL. Trims whitespace, falls back to the default URL when blank,
         * and appends "version.json" when ending with a trailing slash.
         */
        fun normalizeManifestUrl(url: String): String {
            val trimmed = url.trim()
            if (trimmed.isEmpty()) {
                return DEFAULT_MANIFEST_URL + "version.json"
            }
            return if (trimmed.endsWith("/")) {
                trimmed + "version.json"
            } else {
                trimmed
            }
        }

        /**
         * Strips debug package suffix (e.g. "com.selfso.octi.debug" -> "com.selfso.octi").
         */
        fun normalizeApplicationId(appId: String): String = appId.trim().removeSuffix(".debug")

        /**
         * Parses a JSON string representing either a master multi-app catalog (containing an "apps"
         * dictionary) or a single-app manifest. Resolves relative [apkUrl] values against [manifestUrl]
         * and strictly validates required fields (applicationId, versionCode, versionName, apkUrl, sha256).
         */
        fun fromJson(
            jsonString: String,
            manifestUrl: String = DEFAULT_MANIFEST_URL,
            targetApplicationId: String = ""
        ): UpdateManifest {
            val root = JSONObject(jsonString)
            val normalizedTarget = normalizeApplicationId(targetApplicationId)

            val appObj = if (root.has("apps") && root.optJSONObject("apps") != null) {
                val apps = root.getJSONObject("apps")
                val rawTarget = targetApplicationId.trim()
                when {
                    rawTarget.isNotEmpty() && apps.has(rawTarget) -> {
                        apps.getJSONObject(rawTarget)
                    }
                    normalizedTarget.isNotEmpty() && apps.has(normalizedTarget) -> {
                        apps.getJSONObject(normalizedTarget)
                    }
                    targetApplicationId.isBlank() && apps.length() == 1 -> {
                        val singleKey = apps.keys().next()
                        apps.getJSONObject(singleKey)
                    }
                    else -> {
                        throw IllegalArgumentException(
                            "Application '$targetApplicationId' not found in master update catalog"
                        )
                    }
                }
            } else {
                root
            }

            val rawAppId = if (appObj.has("applicationId")) appObj.getString("applicationId").trim() else ""
            if (rawAppId.isEmpty()) {
                throw IllegalArgumentException("Missing or empty applicationId in update manifest")
            }
            val normalizedAppId = normalizeApplicationId(rawAppId)
            if (normalizedTarget.isNotEmpty() && normalizedTarget != normalizedAppId) {
                throw IllegalArgumentException(
                    "Package ID mismatch: expected $normalizedTarget, got $normalizedAppId"
                )
            }

            if (!appObj.has("versionCode")) {
                throw IllegalArgumentException("Missing versionCode in update manifest")
            }
            val versionCode = appObj.getLong("versionCode")
            if (versionCode <= 0L) {
                throw IllegalArgumentException("versionCode must be greater than 0, got $versionCode")
            }

            val versionName = if (appObj.has("versionName")) appObj.getString("versionName").trim() else ""
            if (versionName.isEmpty()) {
                throw IllegalArgumentException("Missing or empty versionName in update manifest")
            }

            val rawApkUrl = if (appObj.has("apkUrl")) appObj.getString("apkUrl").trim() else ""
            if (rawApkUrl.isEmpty()) {
                throw IllegalArgumentException("Missing or empty apkUrl in update manifest")
            }
            val resolvedApkUrl = if (rawApkUrl.startsWith("http://", ignoreCase = true) ||
                rawApkUrl.startsWith("https://", ignoreCase = true)
            ) {
                rawApkUrl
            } else {
                val baseUri = URI(normalizeManifestUrl(manifestUrl))
                baseUri.resolve(rawApkUrl).toString()
            }

            val rawSha256 = if (appObj.has("sha256")) appObj.getString("sha256").trim().lowercase() else ""
            if (!SHA256_HEX_REGEX.matches(rawSha256)) {
                throw IllegalArgumentException(
                    "Invalid sha256 checksum in update manifest: '$rawSha256'"
                )
            }

            val sizeBytes = appObj.optLong("sizeBytes", -1L)
            val minSdk = appObj.optInt("minSdk", 24)
            val targetSdk = appObj.optInt("targetSdk", 35)
            val slug = appObj.optString("slug", "")
            val title = appObj.optString("title", "")
            val pageUrl = appObj.optString("pageUrl", "")
            val publishedAt = appObj.optString("publishedAt", "")
            val releaseNotes = appObj.optString("releaseNotes", "")

            return UpdateManifest(
                applicationId = normalizedAppId,
                versionCode = versionCode,
                versionName = versionName,
                apkUrl = resolvedApkUrl,
                sha256 = rawSha256,
                sizeBytes = sizeBytes,
                minSdk = minSdk,
                targetSdk = targetSdk,
                slug = slug,
                title = title,
                pageUrl = pageUrl,
                publishedAt = publishedAt,
                releaseNotes = releaseNotes
            )
        }
    }
}
