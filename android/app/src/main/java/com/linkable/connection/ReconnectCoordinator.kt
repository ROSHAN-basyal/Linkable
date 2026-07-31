package com.linkable.connection

import com.linkable.debug.DebugEventLog
import com.linkable.discovery.DiscoveryLease
import com.linkable.discovery.NsdDiscoveryManager
import com.linkable.pairing.PairingManager
import com.linkable.pairing.PairingState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Owns background discovery and trusted reconnect policy.
 *
 * NSD remains active only while a trusted desktop needs to be found. Session
 * establishment remains PairingManager's responsibility, which keeps discovery
 * callbacks from launching competing socket attempts.
 */
class ReconnectCoordinator(
    private val discoveryManager: NsdDiscoveryManager,
    private val pairingManager: PairingManager,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var stateJob: Job? = null
    private var devicesJob: Job? = null
    private var fallbackJob: Job? = null

    fun start() {
        if (stateJob != null) return

        stateJob = scope.launch {
            pairingManager.state.collect { state ->
                when {
                    state.canSearchForTrustedPeer() && pairingManager.hasTrustedDevices() -> {
                        discoveryManager.startDiscovery(DiscoveryLease.TRUSTED_RECONNECT)
                    }
                    else -> discoveryManager.stopDiscovery(DiscoveryLease.TRUSTED_RECONNECT)
                }
            }
        }
        devicesJob = scope.launch {
            discoveryManager.devices.collect { devices ->
                pairingManager.autoConnectTrusted(devices)
            }
        }
        fallbackJob = scope.launch {
            pairingManager.state.collectLatest { state ->
                if (!state.canSearchForTrustedPeer() || !pairingManager.hasTrustedDevices()) {
                    return@collectLatest
                }
                delay(FALLBACK_INITIAL_DELAY_MS)
                while (true) {
                    pairingManager.autoConnectTrustedFallback()
                    delay(FALLBACK_INTERVAL_MS)
                }
            }
        }
        DebugEventLog.record("connection", "Trusted reconnect coordinator active")
    }

    fun stop() {
        stateJob?.cancel()
        devicesJob?.cancel()
        fallbackJob?.cancel()
        stateJob = null
        devicesJob = null
        fallbackJob = null
        discoveryManager.stopDiscovery(DiscoveryLease.TRUSTED_RECONNECT)
    }

    private fun PairingState.canSearchForTrustedPeer(): Boolean {
        return this is PairingState.Idle || this is PairingState.Error
    }

    private companion object {
        const val FALLBACK_INITIAL_DELAY_MS = 30_000L
        const val FALLBACK_INTERVAL_MS = 120_000L
    }
}
