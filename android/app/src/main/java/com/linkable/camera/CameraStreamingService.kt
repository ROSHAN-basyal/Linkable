package com.linkable.camera

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.linkable.LinkableApp
import com.linkable.MainActivity
import com.linkable.R
import com.linkable.debug.DebugEventLog

class CameraStreamingService : Service() {
    override fun onCreate() {
        super.onCreate()
        startCameraForeground("Camera sharing is ready")
        DebugEventLog.record("camera", "Camera foreground service ready")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val text = when (intent?.action) {
            ACTION_APPROVAL -> intent.getStringExtra(EXTRA_TEXT) ?: "A paired desktop requests camera access."
            ACTION_ACTIVE -> "Camera stream is active. Keep Linkable open while sharing."
            else -> "Camera sharing is ready"
        }
        startCameraForeground(text)
        return START_STICKY
    }

    override fun onDestroy() {
        if (CameraStreamController.uiState.value.isActive) {
            CameraStreamController.stopAny("camera foreground service stopped")
        }
        DebugEventLog.record("camera", "Camera foreground service stopped")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startCameraForeground(text: String) {
        val notification = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            runCatching {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
                )
            }.onFailure { error ->
                DebugEventLog.record(
                    "camera",
                    "Camera foreground type unavailable; using connected-device service: ${error.message}",
                )
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
                )
            }
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(text: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, LinkableApp.CONNECTION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentTitle("Linkable camera sharing")
            .setContentText(text)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
    }

    companion object {
        private const val NOTIFICATION_ID = 2311
        private const val ACTION_APPROVAL = "com.linkable.camera.APPROVAL"
        private const val ACTION_ACTIVE = "com.linkable.camera.ACTIVE"
        private const val EXTRA_TEXT = "text"

        fun startForApproval(context: Context, desktopName: String) {
            androidx.core.content.ContextCompat.startForegroundService(
                context,
                Intent(context, CameraStreamingService::class.java).apply {
                    action = ACTION_APPROVAL
                    putExtra(EXTRA_TEXT, "$desktopName requests camera access. Tap to review.")
                },
            )
        }

        fun startActive(context: Context) {
            androidx.core.content.ContextCompat.startForegroundService(
                context,
                Intent(context, CameraStreamingService::class.java).apply {
                    action = ACTION_ACTIVE
                },
            )
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CameraStreamingService::class.java))
        }
    }
}
