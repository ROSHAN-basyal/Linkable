package com.linkable.bluetooth

import android.Manifest
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import java.util.concurrent.ConcurrentHashMap

internal class BluetoothConnectedDevicesReader(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val bluetoothManager = appContext.getSystemService(BluetoothManager::class.java)
    private val adapter
        get() = bluetoothManager?.adapter
    private val proxies = ConcurrentHashMap<Int, BluetoothProfile>()
    private val cachedDevices = ConcurrentHashMap<Int, List<BluetoothDevice>>()
    private val listener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
            proxies[profile] = proxy
            cachedDevices[profile] = proxy.safeConnectedDevices()
        }

        override fun onServiceDisconnected(profile: Int) {
            proxies.remove(profile)
            cachedDevices.remove(profile)
        }
    }

    init {
        requestProxy(BluetoothProfile.HEADSET)
        requestProxy(BluetoothProfile.A2DP)
    }

    fun connectedDevices(): List<BluetoothDevice> {
        if (!bluetoothConnectGranted()) return emptyList()
        proxies.forEach { (profile, proxy) ->
            cachedDevices[profile] = proxy.safeConnectedDevices()
        }
        return cachedDevices.values.flatten().distinctBy { device -> device.address }
    }

    fun connectedDevices(profile: Int): List<BluetoothDevice> {
        if (!bluetoothConnectGranted()) return emptyList()
        proxies[profile]?.let { proxy ->
            cachedDevices[profile] = proxy.safeConnectedDevices()
        }
        return cachedDevices[profile].orEmpty()
    }

    fun connectedDeviceForAddress(profile: Int, address: String): BluetoothDevice? {
        val normalizedAddress = address.uppercase()
        return connectedDevices(profile).firstOrNull { device -> device.address.uppercase() == normalizedAddress }
    }

    fun profileConnected(profile: Int, address: String): Boolean {
        return connectedDeviceForAddress(profile, address) != null
    }

    private fun requestProxy(profile: Int) {
        runCatching {
            @Suppress("MissingPermission")
            adapter?.getProfileProxy(appContext, listener, profile)
        }
    }

    private fun BluetoothProfile.safeConnectedDevices(): List<BluetoothDevice> {
        if (!bluetoothConnectGranted()) return emptyList()
        return runCatching {
            @Suppress("MissingPermission")
            connectedDevices.orEmpty()
        }.getOrDefault(emptyList())
    }

    private fun bluetoothConnectGranted(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
    }
}

internal fun BluetoothDevice.safeBluetoothName(): String {
    return runCatching {
        @Suppress("MissingPermission")
        name.orEmpty()
    }.getOrDefault("")
}
