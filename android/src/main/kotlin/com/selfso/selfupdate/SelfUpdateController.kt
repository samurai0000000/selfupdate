/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File

/**
 * Controller orchestrating the end-to-end self-update workflow: checking, downloading,
 * permission prompting, and package installation.
 */
class SelfUpdateController(
    private val context: Context,
    private val scope: CoroutineScope,
    val manifestUrl: String = UpdateManifest.DEFAULT_MANIFEST_URL,
    private val checker: SelfUpdateChecker = SelfUpdateChecker(context, manifestUrl),
    private val downloader: ApkDownloader = ApkDownloader(context),
    private val installer: ApkInstaller = ApkInstaller(context)
) {

    private val _state = MutableStateFlow<UpdateState>(UpdateState.Idle)
    val state: StateFlow<UpdateState> = _state.asStateFlow()

    init {
        scope.launch {
            InstallResultReceiver.installEvents.collect { event ->
                when (event) {
                    is InstallEvent.Success -> {
                        _state.value = UpdateState.Idle
                    }
                    is InstallEvent.Failure -> {
                        val message = event.message ?: "Installation failed with status ${event.statusCode}"
                        val recoverable = (_state.value as? UpdateState.Installing)?.manifest
                        _state.value = UpdateState.Error(message, recoverableManifest = recoverable)
                    }
                    is InstallEvent.PendingUserAction -> {
                        // User confirmation UI launched by InstallResultReceiver
                    }
                }
            }
        }
    }

    /**
     * Queries the update server for available releases matching this application.
     */
    fun checkForUpdates() {
        scope.launch {
            _state.value = UpdateState.Checking
            _state.value = checker.checkForUpdate()
        }
    }

    /**
     * Downloads and initiates installation of the release described by [targetManifest]
     * (or the manifest associated with the current [UpdateState.Available] state).
     */
    fun downloadAndInstall(targetManifest: UpdateManifest? = null) {
        val manifest = targetManifest
            ?: (_state.value as? UpdateState.Available)?.manifest
            ?: (_state.value as? UpdateState.Error)?.recoverableManifest
            ?: return

        scope.launch {
            try {
                _state.value = UpdateState.Downloading(manifest, 0L, manifest.sizeBytes)
                val apkFile = downloader.downloadAndVerify(manifest) { bytesRead, totalBytes ->
                    _state.value = UpdateState.Downloading(manifest, bytesRead, totalBytes)
                }

                if (!installer.canRequestPackageInstalls()) {
                    _state.value = UpdateState.PermissionRequired(manifest, apkFile)
                } else {
                    _state.value = UpdateState.ReadyToInstall(manifest, apkFile)
                    installApkFile(manifest, apkFile)
                }
            } catch (e: Exception) {
                _state.value = UpdateState.Error(
                    e.message ?: "Failed to download update package",
                    recoverableManifest = manifest
                )
            }
        }
    }

    /**
     * Continues installation if the current state is [UpdateState.PermissionRequired]
     * and the unknown sources permission has now been granted.
     */
    fun proceedWithInstallAfterPermission() {
        val current = _state.value
        if (current is UpdateState.PermissionRequired) {
            if (installer.canRequestPackageInstalls()) {
                _state.value = UpdateState.ReadyToInstall(current.manifest, current.apkFile)
                installApkFile(current.manifest, current.apkFile)
            }
        }
    }

    /**
     * Launches the system settings activity allowing the user to grant unknown app install permissions.
     */
    fun openUnknownSourcesSettings() {
        context.startActivity(installer.createManageUnknownAppSourcesIntent())
    }

    /**
     * Initiates installation of an already downloaded and verified APK file.
     */
    fun installReadyApk(apkFile: File, manifest: UpdateManifest) {
        installApkFile(manifest, apkFile)
    }

    /**
     * Resets the controller state back to [UpdateState.Idle].
     */
    fun dismiss() {
        _state.value = UpdateState.Idle
    }

    private fun installApkFile(manifest: UpdateManifest, apkFile: File) {
        try {
            _state.value = UpdateState.Installing(manifest)
            installer.installApk(apkFile, manifest)
        } catch (e: Exception) {
            _state.value = UpdateState.Error(
                e.message ?: "Failed to launch package installer",
                recoverableManifest = manifest
            )
        }
    }
}
