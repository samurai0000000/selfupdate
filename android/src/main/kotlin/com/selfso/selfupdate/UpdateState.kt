/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import java.io.File

/**
 * State machine representing the self-update lifecycle.
 */
sealed interface UpdateState {

    /**
     * No active update check or operation in progress.
     */
    data object Idle : UpdateState

    /**
     * Currently fetching the remote manifest or comparing versions.
     */
    data object Checking : UpdateState

    /**
     * The locally installed version is equal to or newer than the remote manifest.
     */
    data class UpToDate(
        val installedVersionName: String,
        val installedVersionCode: Long,
        val remoteManifest: UpdateManifest? = null
    ) : UpdateState

    /**
     * A newer version is available on the update server.
     */
    data class Available(
        val manifest: UpdateManifest,
        val installedVersionName: String,
        val installedVersionCode: Long
    ) : UpdateState

    /**
     * Actively downloading the update package and computing the SHA-256 digest.
     */
    data class Downloading(
        val manifest: UpdateManifest,
        val bytesRead: Long,
        val totalBytes: Long
    ) : UpdateState {
        val progressFraction: Float?
            get() = if (totalBytes > 0L) {
                (bytesRead.toFloat() / totalBytes.toFloat()).coerceIn(0f, 1f)
            } else {
                null
            }
    }

    /**
     * APK download verified successfully against SHA-256 and staged for installation.
     */
    data class ReadyToInstall(
        val manifest: UpdateManifest,
        val apkFile: File
    ) : UpdateState

    /**
     * Permission to install packages from unknown sources is required before proceeding.
     */
    data class PermissionRequired(
        val manifest: UpdateManifest,
        val apkFile: File
    ) : UpdateState

    /**
     * Installation session is actively being written or committed.
     */
    data class Installing(
        val manifest: UpdateManifest
    ) : UpdateState

    /**
     * An error occurred during check, download, or installation.
     */
    data class Error(
        val message: String,
        val recoverableManifest: UpdateManifest? = null
    ) : UpdateState
}
