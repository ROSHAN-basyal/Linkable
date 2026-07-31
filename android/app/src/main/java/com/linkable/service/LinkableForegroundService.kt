package com.linkable.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.linkable.MainActivity
import com.linkable.LinkableApp
import com.linkable.R
import com.linkable.debug.DebugEventLog

class LinkableForegroundService : Service() {
    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, buildNotification("Keeping Linkable connected"))
        (application as LinkableApp).runtime.startPersistentMode()
        DebugEventLog.record("service", "Foreground service active")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification("Connected features stay active in background"))
        (application as LinkableApp).runtime.startPersistentMode()
        return START_STICKY
    }

    override fun onDestroy() {
        (application as LinkableApp).runtime.stopPersistentMode()
        DebugEventLog.record("service", "Foreground service destroyed")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun buildNotification(text: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, LinkableApp.CONNECTION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle(getString(R.string.connection_notification_title))
            .setContentText(text)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        private const val NOTIFICATION_ID = 2301

        fun start(context: Context) {
            androidx.core.content.ContextCompat.startForegroundService(
                context,
                Intent(context, LinkableForegroundService::class.java),
            )
        }
    }
}
