package com.linkable

import android.content.Context
import com.linkable.connection.ReconnectCoordinator
import com.linkable.debug.DebugEventLog
import com.linkable.discovery.NsdDiscoveryManager
import com.linkable.pairing.PairingManager

class LinkableRuntime(context: Context) {
    val discoveryManager = NsdDiscoveryManager(context.applicationContext)
    val pairingManager = PairingManager(context.applicationContext)
    private val reconnectCoordinator = ReconnectCoordinator(discoveryManager, pairingManager)

    @Volatile
    private var persistentModeStarted = false

    fun startPersistentMode() {
        if (persistentModeStarted) return
        persistentModeStarted = true
        reconnectCoordinator.start()
        DebugEventLog.record("service", "Persistent foreground runtime started in event-driven reconnect mode")
    }

    fun stopPersistentMode() {
        persistentModeStarted = false
        reconnectCoordinator.stop()
        discoveryManager.shutdown()
        pairingManager.shutdown()
        DebugEventLog.record("service", "Persistent foreground runtime stopped")
    }
}
