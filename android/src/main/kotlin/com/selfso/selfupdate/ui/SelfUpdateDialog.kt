/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.selfso.selfupdate.SelfUpdateController
import com.selfso.selfupdate.UpdateManifest
import com.selfso.selfupdate.UpdateState
import java.io.File
import java.util.Locale

/**
 * Formats a raw byte count into a human-readable string (B, KB, MB, GB).
 */
internal fun formatBytes(bytes: Long): String {
    if (bytes <= 0L) return "0 B"
    val units = arrayOf("B", "KB", "MB", "GB")
    var digitGroups = 0
    var size = bytes.toDouble()
    while (size >= 1024.0 && digitGroups < units.lastIndex) {
        size /= 1024.0
        digitGroups++
    }
    return if (digitGroups == 0) {
        "$bytes B"
    } else {
        String.format(Locale.US, "%.1f %s", size, units[digitGroups])
    }
}

/**
 * Controller-backed overload for [SelfUpdateDialog]. Automatically collects [controller.state]
 * and wires user actions directly to the [SelfUpdateController].
 */
@Composable
fun SelfUpdateDialog(
    controller: SelfUpdateController,
    onDismiss: () -> Unit = { controller.dismiss() }
) {
    val state by controller.state.collectAsState()
    SelfUpdateDialog(
        state = state,
        onDownloadAndInstall = { manifest -> controller.downloadAndInstall(manifest) },
        onInstallReadyApk = { file, manifest -> controller.installReadyApk(file, manifest) },
        onOpenPermissionSettings = { controller.openUnknownSourcesSettings() },
        onDismiss = onDismiss
    )
}

/**
 * Jetpack Compose Material3 dialog rendering the self-update state machine transitions.
 */
@Composable
fun SelfUpdateDialog(
    state: UpdateState,
    onDownloadAndInstall: (UpdateManifest) -> Unit,
    onInstallReadyApk: (File, UpdateManifest) -> Unit = { _, _ -> },
    onOpenPermissionSettings: () -> Unit,
    onDismiss: () -> Unit
) {
    when (state) {
        is UpdateState.Available -> {
            AlertDialog(
                onDismissRequest = onDismiss,
                title = {
                    Text(
                        text = "Update Available",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                text = {
                    val scrollState = rememberScrollState()
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .verticalScroll(scrollState)
                    ) {
                        if (state.manifest.title.isNotBlank()) {
                            Text(
                                text = state.manifest.title,
                                style = MaterialTheme.typography.titleMedium
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                        }
                        Text(
                            text = "${state.installedVersionName} (${state.installedVersionCode}) → ${state.manifest.versionName} (${state.manifest.versionCode})",
                            style = MaterialTheme.typography.bodyMedium
                        )
                        if (state.manifest.sizeBytes > 0L) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "Size: ${formatBytes(state.manifest.sizeBytes)}",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        if (state.manifest.sha256.isNotBlank()) {
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "SHA-256: ${state.manifest.sha256.take(16)}…",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        if (state.manifest.releaseNotes.isNotBlank()) {
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Release Notes",
                                style = MaterialTheme.typography.labelLarge
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = state.manifest.releaseNotes,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                },
                confirmButton = {
                    Button(onClick = { onDownloadAndInstall(state.manifest) }) {
                        Text("Download & Install")
                    }
                },
                dismissButton = {
                    TextButton(onClick = onDismiss) {
                        Text("Later")
                    }
                }
            )
        }

        is UpdateState.Downloading -> {
            AlertDialog(
                onDismissRequest = onDismiss,
                title = {
                    Text(
                        text = "Downloading Update…",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                text = {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = "Downloading version ${state.manifest.versionName}…",
                            style = MaterialTheme.typography.bodyMedium
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        val fraction = state.progressFraction
                        if (fraction != null) {
                            LinearProgressIndicator(
                                progress = { fraction },
                                modifier = Modifier.fillMaxWidth()
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "${formatBytes(state.bytesRead)} / ${formatBytes(state.totalBytes)} (${(fraction * 100).toInt()}%)",
                                style = MaterialTheme.typography.bodySmall
                            )
                        } else {
                            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "${formatBytes(state.bytesRead)} downloaded",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                },
                confirmButton = {},
                dismissButton = {
                    TextButton(onClick = onDismiss) {
                        Text("Cancel")
                    }
                }
            )
        }

        is UpdateState.PermissionRequired -> {
            AlertDialog(
                onDismissRequest = onDismiss,
                title = {
                    Text(
                        text = "Permission Required",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                text = {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = "Android requires granting the \"Install unknown apps\" permission for this app before it can install updates from selfso.com.",
                            style = MaterialTheme.typography.bodyMedium
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Please tap \"Open Settings\", enable installation permissions for this app, and return to proceed.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                confirmButton = {
                    Button(onClick = onOpenPermissionSettings) {
                        Text("Open Settings")
                    }
                },
                dismissButton = {
                    Row {
                        OutlinedButton(onClick = { onInstallReadyApk(state.apkFile, state.manifest) }) {
                            Text("Retry Install")
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        TextButton(onClick = onDismiss) {
                            Text("Cancel")
                        }
                    }
                }
            )
        }

        is UpdateState.ReadyToInstall -> {
            AlertDialog(
                onDismissRequest = onDismiss,
                title = {
                    Text(
                        text = "Ready to Install",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                text = {
                    Column(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            text = "Ready to install v${state.manifest.versionName} (${state.manifest.versionCode}).",
                            style = MaterialTheme.typography.bodyMedium
                        )
                        if (state.manifest.releaseNotes.isNotBlank()) {
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = state.manifest.releaseNotes,
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                },
                confirmButton = {
                    Button(onClick = { onInstallReadyApk(state.apkFile, state.manifest) }) {
                        Text("Install Now")
                    }
                },
                dismissButton = {
                    TextButton(onClick = onDismiss) {
                        Text("Cancel")
                    }
                }
            )
        }

        is UpdateState.Installing -> {
            AlertDialog(
                onDismissRequest = {},
                title = {
                    Text(
                        text = "Installing Update…",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                text = {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(28.dp))
                        Text(
                            text = "Launching Android Package Installer…",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                },
                confirmButton = {}
            )
        }

        is UpdateState.Error -> {
            AlertDialog(
                onDismissRequest = onDismiss,
                title = {
                    Text(
                        text = "Update Error",
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.error
                    )
                },
                text = {
                    Text(
                        text = state.message,
                        style = MaterialTheme.typography.bodyMedium
                    )
                },
                confirmButton = {
                    if (state.recoverableManifest != null) {
                        Button(onClick = { onDownloadAndInstall(state.recoverableManifest) }) {
                            Text("Retry")
                        }
                    }
                },
                dismissButton = {
                    TextButton(onClick = onDismiss) {
                        Text("Dismiss")
                    }
                }
            )
        }

        is UpdateState.Idle,
        is UpdateState.Checking,
        is UpdateState.UpToDate -> {
            // No dialog rendered for non-actionable passive states.
        }
    }
}
