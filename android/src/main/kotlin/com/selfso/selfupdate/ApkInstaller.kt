/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import java.io.File
import java.io.FileNotFoundException
import java.security.MessageDigest

/**
 * Handles package installation operations using Android's modern [PackageInstaller] APIs.
 */
class ApkInstaller(
    private val context: Context
) {

    /**
     * Checks whether the hosting application holds permission to install packages.
     * On Android 8.0 (API 26) and above, queries [android.content.pm.PackageManager.canRequestPackageInstalls].
     * On earlier versions, always returns true.
     */
    fun canRequestPackageInstalls(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
    }

    /**
     * Builds an [Intent] directing the user to the system Settings page to grant
     * unknown sources installation permission for this specific app.
     */
    fun createManageUnknownAppSourcesIntent(): Intent {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}")
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        } else {
            Intent(Settings.ACTION_SECURITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }

    /**
     * Commits the provided [apkFile] to Android's [PackageInstaller].
     *
     * Pre-conditions:
     * 1. [apkFile] must exist and have non-zero length.
     * 2. The SHA-256 digest of [apkFile] must match [UpdateManifest.sha256].
     *
     * On completion or failure, the system invokes [InstallResultReceiver].
     */
    fun installApk(apkFile: File, manifest: UpdateManifest) {
        if (!apkFile.exists() || apkFile.length() <= 0L) {
            throw FileNotFoundException("APK file does not exist or is empty: ${apkFile.absolutePath}")
        }

        val computedSha256 = computeFileSha256(apkFile)
        val expectedSha256 = manifest.sha256.trim().lowercase()
        if (computedSha256 != expectedSha256) {
            throw SecurityException(
                "SHA-256 verification failed prior to install: expected $expectedSha256, computed $computedSha256"
            )
        }

        val packageInstaller = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(context.packageName)
        }

        val sessionId = packageInstaller.createSession(params)
        val session = packageInstaller.openSession(sessionId)

        session.use { activeSession ->
            apkFile.inputStream().use { inputStream ->
                activeSession.openWrite("base.apk", 0, apkFile.length()).use { outputStream ->
                    inputStream.copyTo(outputStream)
                    activeSession.fsync(outputStream)
                }
            }

            val intent = Intent(context, InstallResultReceiver::class.java)
            val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            } else {
                PendingIntent.FLAG_UPDATE_CURRENT
            }
            val pendingIntent = PendingIntent.getBroadcast(context, sessionId, intent, flags)
            activeSession.commit(pendingIntent.intentSender)
        }
    }

    private fun computeFileSha256(file: File): String {
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
