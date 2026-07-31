package com.linkable.discovery

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import com.linkable.debug.DebugEventLog
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.net.InetAddress
import java.util.concurrent.ConcurrentHashMap

enum class DiscoveryLease {
    USER_SCAN,
    TRUSTED_RECONNECT,
}

class NsdDiscoveryManager(context: Context) {
    private val appContext = context.applicationContext
    private val nsdManager = appContext.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifiManager = appContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val connectivityManager = appContext.getSystemService(ConnectivityManager::class.java)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val serviceType = "_linkable._tcp."
    private val discovered = ConcurrentHashMap<String, DiscoveredDevice>()
    private val resolvingServices = ConcurrentHashMap.newKeySet<String>()
    private val activeLeases = mutableSetOf<DiscoveryLease>()
    private val _devices = MutableStateFlow<List<DiscoveredDevice>>(emptyList())
    private var discoveryListener: NsdManager.DiscoveryListener? = null
    private var multicastLock: WifiManager.MulticastLock? = null
    private var networkCallbackRegistered = false
    private var desiredRunning = false
    private var stopInProgress = false
    private var pendingRestart = false
    private var pendingClearOnRestart = false
    private var activeWifiNetwork: Network? = null
    private var lastStartFailureLogAtMs = 0L
    private val pendingStartRunnable = Runnable {
        finishPendingRestart()
    }
    private val restartDiscoveryRunnable = Runnable {
        if (networkCallbackRegistered && desiredRunning) {
            DebugEventLog.record("discovery", "Wi-Fi network changed; restarting LAN discovery")
            refreshDiscovery()
        }
    }
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            observeWifiAvailable(network)
        }

        override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
            if (networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                observeWifiAvailable(network)
            }
        }

        override fun onLost(network: Network) {
            mainHandler.post {
                if (network != activeWifiNetwork) return@post
                activeWifiNetwork = null
                discovered.clear()
                resolvingServices.clear()
                emitSnapshot()
                DebugEventLog.record("discovery", "Wi-Fi network lost; discovery will resume when Wi-Fi returns")
            }
        }
    }

    val devices: StateFlow<List<DiscoveredDevice>> = _devices.asStateFlow()

    fun startDiscovery(lease: DiscoveryLease = DiscoveryLease.USER_SCAN) {
        mainHandler.post {
            activeLeases.add(lease)
            desiredRunning = true
            startDiscoveryLocked(clearFirst = false)
        }
    }

    fun stopDiscovery(lease: DiscoveryLease = DiscoveryLease.USER_SCAN) {
        mainHandler.post {
            activeLeases.remove(lease)
            desiredRunning = activeLeases.isNotEmpty()
            if (desiredRunning) return@post
            mainHandler.removeCallbacks(pendingStartRunnable)
            mainHandler.removeCallbacks(restartDiscoveryRunnable)
            pendingRestart = false
            pendingClearOnRestart = false
            stopDiscoveryLocked(finalStop = true)
        }
    }

    fun refreshDiscovery(lease: DiscoveryLease = DiscoveryLease.USER_SCAN) {
        mainHandler.post {
            activeLeases.add(lease)
            desiredRunning = true
            pendingRestart = true
            pendingClearOnRestart = true
            if (discoveryListener != null) {
                stopDiscoveryLocked(finalStop = false)
            } else if (!stopInProgress) {
                finishPendingRestart()
            }
        }
    }

    fun shutdown() {
        mainHandler.post {
            activeLeases.clear()
            desiredRunning = false
            mainHandler.removeCallbacks(pendingStartRunnable)
            mainHandler.removeCallbacks(restartDiscoveryRunnable)
            pendingRestart = false
            pendingClearOnRestart = false
            stopDiscoveryLocked(finalStop = true)
        }
    }

    private fun startDiscoveryLocked(clearFirst: Boolean) {
        if (!desiredRunning) return
        if (discoveryListener != null) {
            return
        }
        if (stopInProgress) {
            pendingRestart = true
            pendingClearOnRestart = pendingClearOnRestart || clearFirst
            return
        }
        if (clearFirst) {
            discovered.clear()
            resolvingServices.clear()
            emitSnapshot()
        }

        ensureMulticastLock()
        ensureNetworkCallback()

        val listener = object : NsdManager.DiscoveryListener {
            override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
                mainHandler.post {
                    logStartFailure(serviceType, errorCode)
                    if (discoveryListener === this) {
                        discoveryListener = null
                    }
                    stopInProgress = false
                    releaseMulticastLock()
                    pendingRestart = desiredRunning
                    if (desiredRunning) {
                        mainHandler.removeCallbacks(pendingStartRunnable)
                        mainHandler.postDelayed(pendingStartRunnable, START_FAILURE_RETRY_MS)
                    } else {
                        releaseNetworkCallback()
                    }
                }
            }

            override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {
                mainHandler.post {
                    DebugEventLog.record("discovery", "Stop failed for $serviceType: $errorCode; resetting local scan state")
                    if (discoveryListener === this) {
                        discoveryListener = null
                    }
                    stopInProgress = false
                    releaseMulticastLock()
                    if (pendingRestart && desiredRunning) {
                        mainHandler.postDelayed(pendingStartRunnable, STOP_FAILURE_RETRY_MS)
                    } else {
                        releaseNetworkCallback()
                    }
                }
            }

            override fun onDiscoveryStarted(serviceType: String?) {
                mainHandler.post {
                    stopInProgress = false
                    DebugEventLog.record("discovery", "Started scan for $serviceType")
                }
            }

            override fun onDiscoveryStopped(serviceType: String?) {
                mainHandler.post {
                    DebugEventLog.record("discovery", "Stopped scan for $serviceType")
                    if (discoveryListener === this) {
                        discoveryListener = null
                    }
                    stopInProgress = false
                    releaseMulticastLock()
                    if (pendingRestart && desiredRunning) {
                        finishPendingRestart()
                    } else {
                        releaseNetworkCallback()
                    }
                }
            }

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                val foundType = serviceInfo.serviceType.orEmpty()
                if (!foundType.startsWith("_linkable._tcp")) {
                    return
                }
                val serviceKey = serviceInfo.serviceName.orEmpty()
                if (serviceKey.isBlank() || !resolvingServices.add(serviceKey)) {
                    return
                }
                nsdManager.resolveService(
                    serviceInfo,
                    object : NsdManager.ResolveListener {
                        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                            resolvingServices.remove(serviceKey)
                            DebugEventLog.record("discovery", "Resolve failed for ${serviceInfo.serviceName}: $errorCode")
                        }

                        override fun onServiceResolved(resolvedServiceInfo: NsdServiceInfo) {
                            resolvingServices.remove(serviceKey)
                            val device = resolvedServiceInfo.toDiscoveredDevice() ?: return
                            val previous = discovered.put(device.serviceName, device)
                            if (previous != device) {
                                DebugEventLog.record("discovery", "Resolved ${device.deviceName} at ${device.endpoint}")
                                emitSnapshot()
                            }
                        }
                    },
                )
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo) {
                resolvingServices.remove(serviceInfo.serviceName)
                if (discovered.remove(serviceInfo.serviceName) != null) {
                    DebugEventLog.record("discovery", "Lost ${serviceInfo.serviceName}")
                    emitSnapshot()
                }
            }
        }

        discoveryListener = listener
        runCatching {
            nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, listener)
        }.onFailure { error ->
            DebugEventLog.record("discovery", "Start threw for $serviceType: ${error.message}; retrying after NSD settles")
            if (discoveryListener === listener) {
                discoveryListener = null
            }
            stopInProgress = false
            releaseMulticastLock()
            pendingRestart = desiredRunning
            if (desiredRunning) {
                mainHandler.removeCallbacks(pendingStartRunnable)
                mainHandler.postDelayed(pendingStartRunnable, START_FAILURE_RETRY_MS)
            } else {
                releaseNetworkCallback()
            }
        }
    }

    private fun stopDiscoveryLocked(finalStop: Boolean) {
        val listener = discoveryListener
        if (listener == null) {
            stopInProgress = false
            releaseMulticastLock()
            if (finalStop) {
                releaseNetworkCallback()
            }
            return
        }
        stopInProgress = true
        runCatching {
            nsdManager.stopServiceDiscovery(listener)
        }.onFailure { error ->
            DebugEventLog.record("discovery", "Stop threw for $serviceType: ${error.message}; resetting local scan state")
            discoveryListener = null
            stopInProgress = false
            releaseMulticastLock()
            if (pendingRestart && desiredRunning) {
                mainHandler.postDelayed(pendingStartRunnable, STOP_FAILURE_RETRY_MS)
            } else if (finalStop) {
                releaseNetworkCallback()
            }
        }
    }

    private fun finishPendingRestart() {
        if (!desiredRunning || !pendingRestart || stopInProgress || discoveryListener != null) {
            return
        }
        val clear = pendingClearOnRestart
        pendingRestart = false
        pendingClearOnRestart = false
        startDiscoveryLocked(clearFirst = clear)
    }

    private fun logStartFailure(type: String?, errorCode: Int) {
        val now = System.currentTimeMillis()
        if (now - lastStartFailureLogAtMs < START_FAILURE_LOG_COOLDOWN_MS) {
            return
        }
        lastStartFailureLogAtMs = now
        DebugEventLog.record("discovery", "Start failed for $type: $errorCode; retrying after NSD settles")
    }

    private fun emitSnapshot() {
        val next = discovered.values.sortedWith(compareBy({ it.deviceName.lowercase() }, { it.endpoint }))
        if (_devices.value != next) {
            _devices.value = next
        }
    }

    private fun ensureMulticastLock() {
        val existing = multicastLock
        if (existing != null) {
            if (!existing.isHeld) {
                existing.acquire()
            }
            return
        }
        val lock = wifiManager.createMulticastLock("linkable-discovery")
        lock.setReferenceCounted(false)
        lock.acquire()
        multicastLock = lock
    }

    private fun releaseMulticastLock() {
        multicastLock?.let { lock ->
            if (lock.isHeld) {
                runCatching { lock.release() }
            }
        }
    }

    private fun ensureNetworkCallback() {
        if (networkCallbackRegistered) return
        activeWifiNetwork = connectivityManager.activeNetwork?.takeIf { network ->
            connectivityManager.getNetworkCapabilities(network)
                ?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        }
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .build()
        runCatching {
            connectivityManager.registerNetworkCallback(request, networkCallback)
            networkCallbackRegistered = true
        }.onFailure { error ->
            DebugEventLog.record("discovery", "Network callback unavailable: ${error.message}")
        }
    }

    private fun releaseNetworkCallback() {
        if (!networkCallbackRegistered) return
        mainHandler.removeCallbacks(pendingStartRunnable)
        mainHandler.removeCallbacks(restartDiscoveryRunnable)
        runCatching {
            connectivityManager.unregisterNetworkCallback(networkCallback)
        }
        networkCallbackRegistered = false
        activeWifiNetwork = null
    }

    private fun observeWifiAvailable(network: Network) {
        mainHandler.post {
            if (!networkCallbackRegistered) return@post
            val previous = activeWifiNetwork
            activeWifiNetwork = network
            if (previous == null) {
                if (desiredRunning && discoveryListener == null && !stopInProgress) {
                    startDiscoveryLocked(clearFirst = true)
                }
                return@post
            }
            if (previous == network) return@post
            mainHandler.removeCallbacks(restartDiscoveryRunnable)
            mainHandler.postDelayed(restartDiscoveryRunnable, NETWORK_CHANGE_DEBOUNCE_MS)
        }
    }

    private fun NsdServiceInfo.toDiscoveredDevice(): DiscoveredDevice? {
        val inetAddress: InetAddress = host ?: return null
        val attrs = readAttributesCompat()
        val serviceName = serviceName ?: return null
        val advertisedHost = attrs["host"]?.decodeToString()?.takeIf { it.isNotBlank() }
        val advertisedPort = attrs["port"]?.decodeToString()?.toIntOrNull()
        return DiscoveredDevice(
            serviceName = serviceName,
            deviceName = attrs["device_name"]?.decodeToString() ?: serviceName,
            host = advertisedHost ?: inetAddress.hostAddress ?: return null,
            port = advertisedPort ?: port,
            protocolVersion = attrs["protocol_version"]?.decodeToString() ?: "unknown",
            deviceId = attrs["device_id"]?.decodeToString() ?: "unknown",
            source = DiscoverySource.NSD,
        )
    }

    @Suppress("UNCHECKED_CAST")
    private fun NsdServiceInfo.readAttributesCompat(): Map<String, ByteArray> {
        val method = runCatching {
            javaClass.methods.firstOrNull { candidate ->
                candidate.name == "getAttributes" && candidate.parameterCount == 0
            }
        }.getOrNull() ?: return emptyMap()

        val raw = runCatching { method.invoke(this) }.getOrNull() as? Map<*, *> ?: return emptyMap()
        return raw.entries.mapNotNull { (key, value) ->
            val name = key as? String ?: return@mapNotNull null
            val bytes = value as? ByteArray ?: return@mapNotNull null
            name to bytes
        }.toMap()
    }

    private companion object {
        const val START_FAILURE_RETRY_MS = 2_500L
        const val STOP_FAILURE_RETRY_MS = 1_000L
        const val START_FAILURE_LOG_COOLDOWN_MS = 10_000L
        const val NETWORK_CHANGE_DEBOUNCE_MS = 1_200L
    }

}
