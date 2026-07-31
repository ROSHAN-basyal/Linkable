package com.linkable.ui

import android.app.Application
import android.content.ComponentName
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.provider.Settings
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.linkable.LinkableApp
import com.linkable.apps.InstalledApp
import com.linkable.apps.InstalledAppsProvider
import com.linkable.bluetooth.BluetoothConnectionStatusProvider
import com.linkable.bluetooth.BluetoothConnectionUiStatus
import com.linkable.calls.TelephonyDiagnosticsProvider
import com.linkable.camera.CameraSessionUiState
import com.linkable.camera.CameraStreamController
import com.linkable.discovery.DiscoveredDevice
import com.linkable.pairing.PairingState
import com.linkable.network.SafeNetworkStore
import com.linkable.network.SafeWifiNetwork
import com.linkable.notifications.PhoneNotificationListener
import com.linkable.protocol.v1.DesktopInputActionType
import com.linkable.protocol.v1.DesktopInputRequest
import com.linkable.protocol.v1.Timestamp
import com.linkable.transfer.TransferDestinationStore
import com.linkable.trust.DevicePermissionStore
import com.linkable.trust.DevicePermissions
import com.linkable.trust.PermissionKey
import kotlinx.coroutines.delay
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.util.UUID

data class DiscoveryUiState(
    val isDiscovering: Boolean = false,
    val pairingState: PairingState = PairingState.Idle,
    val devices: List<DiscoveredDevice> = emptyList(),
    val transferDestinationLabel: String = "/Linkable/{images,videos,pdfs,apks,files}",
    val telephonySummary: String = "",
    val bluetoothStatus: BluetoothConnectionUiStatus = BluetoothConnectionUiStatus(),
    val safeWifi: SafeWifiUiState = SafeWifiUiState(),
    val trustedDevices: List<TrustedDeviceUiState> = emptyList(),
    val selectedDevice: TrustedDeviceUiState? = null,
    val installedApps: List<InstalledApp> = emptyList(),
    val storageAccessGranted: Boolean = false,
    val batteryOptimizationIgnored: Boolean = false,
    val notificationAccessGranted: Boolean = false,
    val cameraSession: CameraSessionUiState = CameraSessionUiState(),
)

data class SafeWifiUiState(
    val allowAllWifi: Boolean = false,
    val locationPermissionGranted: Boolean = false,
    val currentWifiLabel: String = "",
    val networks: List<SafeWifiNetwork> = emptyList(),
    val detail: String = "",
)

data class TrustedDeviceUiState(
    val deviceId: String,
    val deviceName: String,
    val permissions: DevicePermissions,
    val connected: Boolean = false,
    val bluetoothConnected: Boolean = false,
)

private data class DiagnosticsUiSnapshot(
    val transferDestinationLabel: String,
    val bluetoothStatus: BluetoothConnectionUiStatus,
    val safeWifi: SafeWifiUiState,
    val trustedDevices: List<TrustedDeviceUiState>,
    val selectedDeviceId: String?,
    val installedApps: List<InstalledApp>,
    val storageAccessGranted: Boolean,
    val batteryOptimizationIgnored: Boolean,
    val notificationAccessGranted: Boolean,
)

private data class DeviceManagementSnapshot(
    val selectedDeviceId: String?,
    val installedApps: List<InstalledApp>,
)

class DiscoveryViewModel(application: Application) : AndroidViewModel(application) {
    private val appContext = application.applicationContext
    private val runtime = (application as LinkableApp).runtime
    private val discoveryManager = runtime.discoveryManager
    private val pairingManager = runtime.pairingManager
    private val telephonyDiagnosticsProvider = TelephonyDiagnosticsProvider(application.applicationContext)
    private val bluetoothStatusProvider = BluetoothConnectionStatusProvider(application.applicationContext)
    private val safeNetworkStore = SafeNetworkStore(application.applicationContext)
    private val devicePermissionStore = DevicePermissionStore(application.applicationContext)
    private val installedAppsProvider = InstalledAppsProvider(application.applicationContext)
    private val isDiscovering = MutableStateFlow(false)
    private val bluetoothStatus = MutableStateFlow(bluetoothStatusProvider.snapshot(null))
    private val safeWifiState = MutableStateFlow(safeWifiUiState())
    private val selectedDeviceId = MutableStateFlow<String?>(null)
    private val installedAppsState = MutableStateFlow(installedAppsProvider.installedApps())
    private val permissionStateVersion = MutableStateFlow(0)
    private var scanJob: Job? = null
    private val deviceManagementState = combine(
        selectedDeviceId,
        installedAppsState,
        permissionStateVersion,
    ) { selected, installedApps, _ ->
        DeviceManagementSnapshot(selected, installedApps)
    }
    private val diagnosticsState = combine(
        TransferDestinationStore.label,
        bluetoothStatus,
        safeWifiState,
        deviceManagementState,
    ) { transferDestination, bluetooth, safeWifi, deviceManagement ->
        val trustedDevices = trustedDeviceUiState()
        DiagnosticsUiSnapshot(
            transferDestinationLabel = transferDestination,
            bluetoothStatus = bluetooth,
            safeWifi = safeWifi,
            trustedDevices = trustedDevices,
            selectedDeviceId = deviceManagement.selectedDeviceId,
            installedApps = deviceManagement.installedApps,
            storageAccessGranted = storageAccessGranted(),
            batteryOptimizationIgnored = batteryOptimizationIgnored(),
            notificationAccessGranted = notificationAccessGranted(),
        )
    }

    val uiState: StateFlow<DiscoveryUiState> = combine(
        isDiscovering,
        discoveryManager.devices,
        diagnosticsState,
        pairingManager.state,
        CameraStreamController.uiState,
    ) { discovering, devices, diagnostics, pairingState, cameraSession ->
        DiscoveryUiState(
            isDiscovering = discovering,
            pairingState = pairingState,
            devices = devices,
            transferDestinationLabel = diagnostics.transferDestinationLabel,
            telephonySummary = telephonyDiagnosticsProvider.summary(),
            bluetoothStatus = diagnostics.bluetoothStatus,
            safeWifi = diagnostics.safeWifi,
            trustedDevices = diagnostics.trustedDevices,
            selectedDevice = diagnostics.trustedDevices.firstOrNull { it.deviceId == diagnostics.selectedDeviceId },
            installedApps = diagnostics.installedApps,
            storageAccessGranted = diagnostics.storageAccessGranted,
            batteryOptimizationIgnored = diagnostics.batteryOptimizationIgnored,
            notificationAccessGranted = diagnostics.notificationAccessGranted,
            cameraSession = cameraSession,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = DiscoveryUiState(),
    )

    init {
        runtime.startPersistentMode()
        viewModelScope.launch {
            pairingManager.state.collectLatest {
                refreshRuntimeDiagnostics()
            }
        }
        viewModelScope.launch {
            while (true) {
                refreshRuntimeDiagnostics()
                delay(DIAGNOSTICS_REFRESH_MS)
            }
        }
    }

    fun scanForDesktops() {
        scanJob?.cancel()
        discoveryManager.refreshDiscovery()
        isDiscovering.value = true
        scanJob = viewModelScope.launch {
            delay(30_000)
            stopDiscovery()
        }
    }

    fun stopDiscovery() {
        scanJob?.cancel()
        scanJob = null
        discoveryManager.stopDiscovery()
        isDiscovering.value = false
    }

    fun refreshDiscovery() {
        scanForDesktops()
    }

    fun startPairing(device: DiscoveredDevice) {
        scanJob?.cancel()
        scanJob = null
        discoveryManager.stopDiscovery()
        isDiscovering.value = false
        pairingManager.startPairing(device)
    }

    fun unpairDevice(deviceId: String) {
        pairingManager.unpairDevice(deviceId)
        if (selectedDeviceId.value == deviceId) {
            selectedDeviceId.value = null
        }
        permissionStateVersion.value += 1
        refreshSafeWifi()
    }

    fun refreshSafeWifi() {
        safeWifiState.value = safeWifiUiState()
    }

    fun setAllowPairingOnAllWifi(allowAll: Boolean) {
        safeNetworkStore.setAllowAllWifi(allowAll)
        val detail = if (allowAll) {
            "Pairing and reconnect are allowed on all Wi-Fi networks."
        } else if (pairingManager.trustCurrentWifiForTrustedDevices()) {
            "Safe Wi-Fi is enabled. Current Wi-Fi is available for strict pairing and reconnect."
        } else {
            "Safe Wi-Fi is enabled, but the current Wi-Fi could not be read. Grant Location while using the app and keep Wi-Fi connected."
        }
        safeWifiState.value = safeWifiUiState(detail)
    }

    fun setSafeWifiEnabled(fingerprint: String, enabled: Boolean) {
        safeNetworkStore.setNetworkEnabled(fingerprint, enabled)
        safeWifiState.value = safeWifiUiState("Safe Wi-Fi list updated.")
    }

    fun selectTrustedDevice(deviceId: String?) {
        selectedDeviceId.value = deviceId
    }

    fun setDevicePermission(deviceId: String, key: PermissionKey, enabled: Boolean) {
        devicePermissionStore.setPermission(deviceId, key, enabled)
        pairingManager.onDevicePermissionsChanged(deviceId)
        permissionStateVersion.value += 1
    }

    fun setSharedApp(packageName: String, shared: Boolean) {
        installedAppsProvider.setShared(packageName, shared)
        installedAppsState.value = installedAppsProvider.installedApps(selectedDeviceId.value.orEmpty())
    }

    fun setNotificationBlocked(deviceId: String, packageName: String, blocked: Boolean) {
        installedAppsProvider.setNotificationBlocked(deviceId, packageName, blocked)
        installedAppsState.value = installedAppsProvider.installedApps(deviceId)
        permissionStateVersion.value += 1
    }

    fun refreshPermissions() {
        installedAppsState.value = installedAppsProvider.installedApps(selectedDeviceId.value.orEmpty())
        permissionStateVersion.value += 1
    }

    fun sendFileToDesktop(uri: Uri) {
        pairingManager.sendFile(uri)
    }

    fun sendDesktopText(text: String) {
        if (text.isBlank()) return
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_TEXT)
                .setText(text)
                .build(),
        )
    }

    fun sendDesktopKeyCombo(keys: List<String>) {
        if (keys.isEmpty()) return
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_KEY_COMBO)
                .addAllKeyCombo(keys)
                .build(),
        )
    }

    fun moveDesktopPointer(dx: Int, dy: Int) {
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_POINTER_MOVE)
                .setPointerDx(dx)
                .setPointerDy(dy)
                .build(),
        )
    }

    fun clickDesktopPointer(button: Int) {
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_POINTER_CLICK)
                .setPointerButton(button)
                .build(),
        )
    }

    fun scrollDesktopPointer(deltaY: Int) {
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_POINTER_SCROLL)
                .setScrollY(deltaY)
                .build(),
        )
    }

    fun setDesktopVolume(percent: Int) {
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_VOLUME_SET)
                .setVolumePercent(percent)
                .build(),
        )
    }

    fun setDesktopMicMuted(muted: Boolean) {
        pairingManager.sendDesktopInput(
            desktopInputRequest(DesktopInputActionType.DESKTOP_INPUT_ACTION_TYPE_MIC_MUTE_SET)
                .setMicMuted(muted)
                .build(),
        )
    }

    fun approvePendingCameraRequest() {
        pairingManager.approvePendingCameraRequest()
    }

    fun rejectPendingCameraRequest() {
        pairingManager.rejectPendingCameraRequest()
    }

    fun stopCameraFromPhone() {
        pairingManager.stopCameraFromPhone()
    }

    private fun lanPeerName(state: PairingState): String? {
        return when (state) {
            is PairingState.Success -> state.deviceName
            is PairingState.Connecting -> state.deviceName
            is PairingState.AwaitingCodeEntry -> state.deviceName
            is PairingState.PairingInProgress -> state.deviceName
            is PairingState.Reconnecting -> state.deviceName
            is PairingState.Error,
            PairingState.Idle -> null
        }
    }

    private fun desktopInputRequest(actionType: DesktopInputActionType): DesktopInputRequest.Builder {
        return DesktopInputRequest.newBuilder()
            .setRequestId(UUID.randomUUID().toString())
            .setActionType(actionType)
            .setSentAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
    }

    private fun safeWifiUiState(detail: String = ""): SafeWifiUiState {
        val snapshot = safeNetworkStore.snapshot()
        return SafeWifiUiState(
            allowAllWifi = snapshot.allowAllWifi,
            locationPermissionGranted = snapshot.locationPermissionGranted,
            currentWifiLabel = snapshot.currentWifiLabel,
            networks = snapshot.networks,
            detail = detail,
        )
    }

    private fun refreshRuntimeDiagnostics() {
        val nextBluetooth = bluetoothStatusProvider.snapshot(lanPeerName(pairingManager.state.value))
        if (bluetoothStatus.value != nextBluetooth) {
            bluetoothStatus.value = nextBluetooth
        }
        val nextSafeWifi = safeWifiUiState()
        if (safeWifiState.value != nextSafeWifi) {
            safeWifiState.value = nextSafeWifi
        }
    }

    private fun trustedDeviceUiState(): List<TrustedDeviceUiState> {
        val state = pairingManager.state.value
        val connectedDeviceId = (state as? PairingState.Success)?.deviceId
        val bluetoothConnected = bluetoothStatus.value.connectedToLanPeer
        return pairingManager.trustedDevices().map { device ->
            TrustedDeviceUiState(
                deviceId = device.deviceId,
                deviceName = device.deviceName,
                permissions = devicePermissionStore.permissionsFor(device.deviceId),
                connected = device.deviceId == connectedDeviceId,
                bluetoothConnected = device.deviceId == connectedDeviceId && bluetoothConnected,
            )
        }
    }

    private fun storageAccessGranted(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager()
    }

    private fun batteryOptimizationIgnored(): Boolean {
        val powerManager = appContext.getSystemService(Context.POWER_SERVICE) as PowerManager
        return powerManager.isIgnoringBatteryOptimizations(appContext.packageName)
    }

    private fun notificationAccessGranted(): Boolean {
        val enabled = Settings.Secure.getString(appContext.contentResolver, "enabled_notification_listeners").orEmpty()
        val expected = ComponentName(appContext, PhoneNotificationListener::class.java)
        return enabled.split(':').any { value ->
            ComponentName.unflattenFromString(value)?.let { component ->
                component.packageName == expected.packageName && component.className == expected.className
            } == true
        }
    }

    private companion object {
        const val DIAGNOSTICS_REFRESH_MS = 30_000L
    }
}
