/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import androidx.core.content.IntentCompat
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * Event model describing the outcome of a package installer session.
 */
sealed interface InstallEvent {
    data class PendingUserAction(val intent: Intent) : InstallEvent
    data object Success : InstallEvent
    data class Failure(val statusCode: Int, val message: String?) : InstallEvent
}

/**
 * BroadcastReceiver registered to receive callbacks from [PackageInstaller.Session.commit].
 * Dispatches installation outcomes to registered observers via [installEvents].
 */
class InstallResultReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirmIntent = IntentCompat.getParcelableExtra(
                    intent,
                    Intent.EXTRA_INTENT,
                    Intent::class.java
                )
                if (confirmIntent != null) {
                    confirmIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(confirmIntent)
                    notifyEvent(InstallEvent.PendingUserAction(confirmIntent))
                }
            }
            PackageInstaller.STATUS_SUCCESS -> {
                notifyEvent(InstallEvent.Success)
            }
            else -> {
                val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
                notifyEvent(InstallEvent.Failure(status, message))
            }
        }
    }

    companion object {
        private val _installEvents = MutableSharedFlow<InstallEvent>(extraBufferCapacity = 16)
        val installEvents: SharedFlow<InstallEvent> = _installEvents.asSharedFlow()

        internal fun notifyEvent(event: InstallEvent) {
            _installEvents.tryEmit(event)
        }
    }
}
