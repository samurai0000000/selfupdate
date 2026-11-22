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
import androidx.compose.material3.Button
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.selfso.selfupdate.R
import com.selfso.selfupdate.SelfUpdateController
import com.selfso.selfupdate.UpdateManifest
import com.selfso.selfupdate.UpdateState

/**
 * Creates and remembers a [SelfUpdateController] tied to the current Composable lifecycle.
 * If [checkOnLaunch] is true, triggers an initial update check against [manifestUrl].
 */
@Composable
fun rememberSelfUpdateController(
    manifestUrl: String = UpdateManifest.DEFAULT_MANIFEST_URL,
    checkOnLaunch: Boolean = true
): SelfUpdateController {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val controller = remember(manifestUrl) {
        SelfUpdateController(context.applicationContext, scope, manifestUrl)
    }

    if (checkOnLaunch) {
        LaunchedEffect(manifestUrl) {
            controller.checkForUpdates()
        }
    }

    return controller
}

/**
 * Headless or container composable hosting the [SelfUpdateController] lifecycle and dialog.
 */
@Composable
fun SelfUpdateHost(
    manifestUrl: String = UpdateManifest.DEFAULT_MANIFEST_URL,
    checkOnLaunch: Boolean = true,
    controller: SelfUpdateController = rememberSelfUpdateController(manifestUrl, checkOnLaunch),
    content: @Composable (SelfUpdateController) -> Unit = {}
) {
    SelfUpdateDialog(controller = controller)
    content(controller)
}

/**
 * Material3 banner rendering self-update status cards inline. Automatically triggers
 * [SelfUpdateDialog] when an update action is initiated or actively in flight.
 */
@Composable
fun SelfUpdateBanner(
    controller: SelfUpdateController,
    modifier: Modifier = Modifier,
    showWhenUpToDate: Boolean = false
) {
    val state by controller.state.collectAsState()
    var showDialog by remember { mutableStateOf(false) }

    val shouldDisplayDialog = showDialog ||
        state is UpdateState.Downloading ||
        state is UpdateState.PermissionRequired ||
        state is UpdateState.ReadyToInstall ||
        state is UpdateState.Installing

    if (shouldDisplayDialog) {
        SelfUpdateDialog(
            controller = controller,
            onDismiss = {
                showDialog = false
                controller.dismiss()
            }
        )
    }

    when (val currentState = state) {
        is UpdateState.Available -> {
            OutlinedCard(
                modifier = modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.selfupdate_title_available),
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = stringResource(
                            R.string.selfupdate_banner_available_body,
                            currentState.manifest.versionName,
                            currentState.installedVersionName
                        ),
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(onClick = { controller.dismiss() }) {
                            Text(stringResource(R.string.selfupdate_action_later))
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Button(onClick = {
                            showDialog = true
                            controller.downloadAndInstall(currentState.manifest)
                        }) {
                            Text(stringResource(R.string.selfupdate_action_update))
                        }
                    }
                }
            }
        }

        is UpdateState.Downloading -> {
            OutlinedCard(
                modifier = modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(
                            R.string.selfupdate_banner_downloading_title,
                            currentState.manifest.versionName
                        ),
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    val fraction = currentState.progressFraction
                    if (fraction != null) {
                        LinearProgressIndicator(
                            progress = { fraction },
                            modifier = Modifier.fillMaxWidth()
                        )
                    } else {
                        LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = if (fraction != null) {
                                stringResource(
                                    R.string.selfupdate_banner_progress_pair,
                                    formatBytes(currentState.bytesRead),
                                    formatBytes(currentState.totalBytes)
                                )
                            } else {
                                formatBytes(currentState.bytesRead)
                            },
                            style = MaterialTheme.typography.bodySmall
                        )
                        TextButton(onClick = { showDialog = true }) {
                            Text(stringResource(R.string.selfupdate_action_details))
                        }
                    }
                }
            }
        }

        is UpdateState.PermissionRequired -> {
            OutlinedCard(
                modifier = modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.selfupdate_title_permission_required),
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = stringResource(R.string.selfupdate_banner_permission_body),
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(onClick = { controller.dismiss() }) {
                            Text(stringResource(R.string.selfupdate_action_cancel))
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Button(onClick = { controller.openUnknownSourcesSettings() }) {
                            Text(stringResource(R.string.selfupdate_action_settings))
                        }
                    }
                }
            }
        }

        is UpdateState.ReadyToInstall -> {
            OutlinedCard(
                modifier = modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.selfupdate_title_update_ready),
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = stringResource(
                            R.string.selfupdate_banner_ready_body,
                            currentState.manifest.versionName
                        ),
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(onClick = { controller.dismiss() }) {
                            Text(stringResource(R.string.selfupdate_action_cancel))
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Button(onClick = {
                            controller.installReadyApk(currentState.apkFile, currentState.manifest)
                        }) {
                            Text(stringResource(R.string.selfupdate_action_install_now))
                        }
                    }
                }
            }
        }

        is UpdateState.Installing -> {
            OutlinedCard(
                modifier = modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors()
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp))
                    Text(
                        text = stringResource(R.string.selfupdate_banner_launching_installer),
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }

        is UpdateState.Error -> {
            OutlinedCard(
                modifier = modifier.fillMaxWidth(),
                colors = CardDefaults.outlinedCardColors()
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.selfupdate_title_error),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.error
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = currentState.message,
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End
                    ) {
                        TextButton(onClick = { controller.dismiss() }) {
                            Text(stringResource(R.string.selfupdate_action_dismiss))
                        }
                        if (currentState.recoverableManifest != null) {
                            Spacer(modifier = Modifier.width(8.dp))
                            Button(onClick = {
                                controller.downloadAndInstall(currentState.recoverableManifest)
                            }) {
                                Text(stringResource(R.string.selfupdate_action_retry))
                            }
                        }
                    }
                }
            }
        }

        is UpdateState.UpToDate -> {
            if (showWhenUpToDate) {
                OutlinedCard(
                    modifier = modifier.fillMaxWidth(),
                    colors = CardDefaults.outlinedCardColors()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = stringResource(R.string.selfupdate_title_up_to_date),
                                style = MaterialTheme.typography.titleMedium
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = stringResource(
                                    R.string.selfupdate_banner_version_code,
                                    currentState.installedVersionName,
                                    currentState.installedVersionCode
                                ),
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            TextButton(onClick = {
                                showDialog = true
                                controller.reinstall()
                            }) {
                                Text(stringResource(R.string.selfupdate_action_reinstall))
                            }
                            Spacer(modifier = Modifier.width(4.dp))
                            TextButton(onClick = { controller.checkForUpdates() }) {
                                Text(stringResource(R.string.selfupdate_action_check_again))
                            }
                        }
                    }
                }
            }
        }

        is UpdateState.Checking -> {
            if (showWhenUpToDate) {
                OutlinedCard(
                    modifier = modifier.fillMaxWidth(),
                    colors = CardDefaults.outlinedCardColors()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp))
                        Text(
                            text = stringResource(R.string.selfupdate_banner_checking),
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }
        }

        is UpdateState.Idle -> {
            if (showWhenUpToDate) {
                OutlinedCard(
                    modifier = modifier.fillMaxWidth(),
                    colors = CardDefaults.outlinedCardColors()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = stringResource(R.string.selfupdate_banner_idle_prompt),
                            style = MaterialTheme.typography.bodyMedium
                        )
                        TextButton(onClick = { controller.checkForUpdates() }) {
                            Text(stringResource(R.string.selfupdate_action_check_now))
                        }
                    }
                }
            }
        }
    }
}
