package com.linkable.bluetooth

import android.Manifest
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat

data class BluetoothConnectionUiStatus(
    val adapterAvailable: Boolean = false,
    val adapterEnabled: Boolean = false,
    val connectPermissionGranted: Boolean = false,
    val connectedToLanPeer: Boolean = false,
    val a2dpConnectedToLanPeer: Boolean = false,
    val headsetConnectedToLanPeer: Boolean = false,
    val routeWarning: String = "",
    val connectedDeviceName: String = "",
    val connectedDeviceAddress: String = "",
    val detail: String = "Bluetooth status not checked yet.",
)

class BluetoothConnectionStatusProvider(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val bluetoothManager = appContext.getSystemService(BluetoothManager::class.java)
    private val connectedDevicesReader = BluetoothConnectedDevicesReader(appContext)
    private val adapter
        get() = bluetoothManager?.adapter

    fun snapshot(lanPeerName: String?): BluetoothConnectionUiStatus {
        val bluetoothAdapter = adapter
        val connectGranted = bluetoothConnectGranted()
        if (bluetoothAdapter == null) {
            return BluetoothConnectionUiStatus(detail = "This phone has no Bluetooth adapter.")
        }
        if (!connectGranted) {
            return BluetoothConnectionUiStatus(
                adapterAvailable = true,
                detail = "Nearby devices permission is required to check Bluetooth connection status.",
            )
        }

        @Suppress("MissingPermission")
        val enabled = bluetoothAdapter.isEnabled
        if (!enabled) {
            return BluetoothConnectionUiStatus(
                adapterAvailable = true,
                connectPermissionGranted = true,
                detail = "Bluetooth is off. Pair/connect manually in Android Bluetooth settings when call audio is needed.",
            )
        }

        val connectedDevices = connectedDevicesReader.connectedDevices()
        val peer = lanPeerName.orEmpty()
        val matchingDevice = connectedDevices.firstOrNull { device ->
            identitiesMatch(device.safeBluetoothName(), peer)
        }
        val connectedDevice = matchingDevice ?: connectedDevices.firstOrNull()
        val connectedName = connectedDevice?.safeBluetoothName().orEmpty()
        val connectedAddress = connectedDevice?.address.orEmpty()
        val connectedToLanPeer = matchingDevice != null && peer.isNotBlank()
        val a2dpConnected = connectedToLanPeer &&
            connectedDevicesReader.connectedDevices(BluetoothProfile.A2DP).any { device -> identitiesMatch(device.safeBluetoothName(), peer) }
        val headsetConnected = connectedToLanPeer &&
            connectedDevicesReader.connectedDevices(BluetoothProfile.HEADSET).any { device -> identitiesMatch(device.safeBluetoothName(), peer) }
        val routeWarning = if (a2dpConnected) {
            "Laptop is connected as Media audio (A2DP). Install Phone-safe Bluetooth mode on desktop, then reconnect Bluetooth."
        } else {
            ""
        }
        return BluetoothConnectionUiStatus(
            adapterAvailable = true,
            adapterEnabled = true,
            connectPermissionGranted = true,
            connectedToLanPeer = connectedToLanPeer,
            a2dpConnectedToLanPeer = a2dpConnected,
            headsetConnectedToLanPeer = headsetConnected,
            routeWarning = routeWarning,
            connectedDeviceName = connectedName,
            connectedDeviceAddress = connectedAddress,
            detail = when {
                connectedToLanPeer && a2dpConnected -> "Bluetooth is connected to the current LAN laptop, but Media audio is still enabled."
                connectedToLanPeer -> "Manual Bluetooth connection is active with the current LAN laptop."
                connectedDevices.isNotEmpty() -> "Bluetooth is connected to ${connectedName.ifBlank { connectedAddress }}, not verified as the current LAN laptop."
                peer.isBlank() -> "Bluetooth is on. Connect to a laptop over LAN to verify same-device status."
                else -> "Bluetooth is on, but the current LAN laptop is not connected over Bluetooth."
            },
        )
    }

    private fun bluetoothConnectGranted(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
    }

}

private fun identitiesMatch(left: String, right: String): Boolean {
    val normalizedLeft = normalizeIdentity(left)
    val normalizedRight = normalizeIdentity(right)
    return normalizedLeft.isNotBlank() &&
        normalizedRight.isNotBlank() &&
        (normalizedLeft == normalizedRight || normalizedLeft.contains(normalizedRight) || normalizedRight.contains(normalizedLeft))
}

private fun normalizeIdentity(value: String): String {
    return value.lowercase().replace(Regex("[^0-9a-z]+"), "")
}
