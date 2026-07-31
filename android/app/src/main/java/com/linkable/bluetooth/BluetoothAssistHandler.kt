package com.linkable.bluetooth

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.linkable.protocol.v1.BluetoothAssistDesktopStatus
import com.linkable.protocol.v1.BluetoothAssistPhoneStatus
import com.linkable.protocol.v1.BluetoothBondState
import com.linkable.protocol.v1.Timestamp

class BluetoothAssistHandler(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val bluetoothManager = appContext.getSystemService(BluetoothManager::class.java)
    private val connectedDevicesReader = BluetoothConnectedDevicesReader(appContext)
    private val adapter: BluetoothAdapter?
        get() = bluetoothManager?.adapter

    fun handleDesktopStatus(status: BluetoothAssistDesktopStatus): BluetoothAssistPhoneStatus {
        val bluetoothAdapter = adapter
        val connectGranted = bluetoothConnectGranted()
        val scanGranted = bluetoothScanGranted()
        val builder = BluetoothAssistPhoneStatus.newBuilder()
            .setRequestId(status.requestId)
            .setBluetoothConnectPermissionGranted(connectGranted)
            .setBluetoothScanPermissionGranted(scanGranted)
            .setAdapterAvailable(bluetoothAdapter != null)
            .setDesktopAddress(status.adapterAddress)
            .setGeneratedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())

        if (bluetoothAdapter == null) {
            return builder
                .setDetail("phone has no Bluetooth adapter")
                .build()
        }

        if (!connectGranted) {
            return builder
                .setAdapterEnabled(false)
                .setDetail("BLUETOOTH_CONNECT permission missing; grant Nearby devices permission")
                .build()
        }

        @Suppress("MissingPermission")
        val phoneName = bluetoothAdapter.name.orEmpty()
        @Suppress("MissingPermission")
        val enabled = bluetoothAdapter.isEnabled
        builder.setAdapterName(phoneName)
        builder.setAdapterEnabled(enabled)

        if (!enabled) {
            return builder
                .setBluetoothSettingsOpened(false)
                .setDetail("Bluetooth is off; enable and pair manually in Android Bluetooth settings")
                .build()
        }

        if (!status.adapterAvailable || !status.powered || status.adapterAddress.isBlank()) {
            return builder
                .setDetail("desktop did not provide an available powered Bluetooth adapter")
                .build()
        }

        val device = runCatching { bluetoothAdapter.getRemoteDevice(status.adapterAddress) }.getOrNull()
        if (device == null) {
            return builder
                .setDetail("desktop Bluetooth address is invalid: ${status.adapterAddress}")
                .build()
        }

        val bondState = bondState(device)
        val desktopLabel = status.adapterAlias.ifBlank { status.adapterAddress }
        builder.setDesktopBondState(bondState)
        val connectedDevice = connectedDesktopDevice(status.adapterAddress)
        val desktopConnected = connectedDevice != null
        val a2dpConnected = connectedDevicesReader.profileConnected(BluetoothProfile.A2DP, status.adapterAddress)
        val headsetConnected = connectedDevicesReader.profileConnected(BluetoothProfile.HEADSET, status.adapterAddress)
        val routeWarning = if (desktopConnected && a2dpConnected) {
            "Laptop is connected as Bluetooth media audio (A2DP); install phone-safe Bluetooth mode on desktop and reconnect Bluetooth."
        } else {
            ""
        }
        return builder
            .setBondRequestStarted(false)
            .setBluetoothSettingsOpened(false)
            .setDesktopConnected(desktopConnected)
            .setDesktopA2DpConnected(a2dpConnected)
            .setDesktopHeadsetConnected(headsetConnected)
            .setConnectedDesktopName(connectedDevice?.safeBluetoothName().orEmpty())
            .setConnectedDesktopAddress(connectedDevice?.address.orEmpty())
            .setRouteWarning(routeWarning)
            .setDetail(
                when {
                    desktopConnected && a2dpConnected -> "manual Bluetooth connection active with $desktopLabel, but media audio is still enabled"
                    desktopConnected -> "manual Bluetooth connection active with $desktopLabel"
                    bondState == BluetoothBondState.BLUETOOTH_BOND_STATE_BONDED -> "paired manually with $desktopLabel, but not connected"
                    else -> "not paired; pair manually in Android Bluetooth settings"
                },
            )
            .build()
    }

    private fun bluetoothConnectGranted(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
    }

    private fun bluetoothScanGranted(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED
    }

    private fun bondState(device: BluetoothDevice): BluetoothBondState {
        val state = runCatching {
            @Suppress("MissingPermission")
            device.bondState
        }.getOrDefault(BluetoothDevice.BOND_NONE)
        return when (state) {
            BluetoothDevice.BOND_BONDED -> BluetoothBondState.BLUETOOTH_BOND_STATE_BONDED
            BluetoothDevice.BOND_BONDING -> BluetoothBondState.BLUETOOTH_BOND_STATE_BONDING
            BluetoothDevice.BOND_NONE -> BluetoothBondState.BLUETOOTH_BOND_STATE_NONE
            else -> BluetoothBondState.BLUETOOTH_BOND_STATE_UNSPECIFIED
        }
    }

    private fun connectedDesktopDevice(desktopAddress: String): BluetoothDevice? {
        val normalizedAddress = desktopAddress.uppercase()
        return connectedDevicesReader.connectedDevices()
            .firstOrNull { device -> device.address.uppercase() == normalizedAddress }
    }
}
