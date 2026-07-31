package com.linkable

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.linkable.transfer.TransferDestinationStore

class LinkableApp : Application() {
    val runtime: LinkableRuntime by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        LinkableRuntime(this)
    }

    override fun onCreate() {
        super.onCreate()
        TransferDestinationStore.initialize()
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CONNECTION_CHANNEL_ID,
            getString(R.string.connection_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.connection_channel_description)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        const val CONNECTION_CHANNEL_ID = "linkable_connection"
    }
}
