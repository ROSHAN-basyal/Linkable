package com.linkable.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.linkable.debug.DebugEventLog

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) {
            return
        }
        runCatching {
            LinkableForegroundService.start(context)
        }.onSuccess {
            DebugEventLog.record("service", "Foreground service requested after boot")
        }.onFailure { error ->
            DebugEventLog.record("service", "Boot service start failed: ${error.message}")
        }
    }
}
