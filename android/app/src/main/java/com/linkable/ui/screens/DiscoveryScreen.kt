package com.linkable.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.ContentPaste
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.DesktopWindows
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.Mouse
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.NotificationsOff
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Security
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.ui.Alignment
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.activity.compose.BackHandler
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.roundToInt
import com.linkable.debug.DebugEvent
import com.linkable.debug.DebugEventLog
import com.linkable.discovery.DiscoveredDevice
import com.linkable.pairing.PairingState
import com.linkable.ui.DiscoveryUiState
import com.linkable.ui.SafeWifiUiState
import com.linkable.ui.TrustedDeviceUiState
import com.linkable.apps.InstalledApp
import com.linkable.camera.CameraSessionUiState
import com.linkable.protocol.v1.CameraFacing
import com.linkable.protocol.v1.CameraRoute
import com.linkable.trust.PermissionKey

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiscoveryScreen(
    uiState: DiscoveryUiState,
    onStopDiscovery: () -> Unit,
    onRefreshDiscovery: () -> Unit,
    onScanForDesktops: () -> Unit,
    onConnect: (DiscoveredDevice) -> Unit,
    onOpenNotificationSettings: () -> Unit,
    onSendFileToDesktop: () -> Unit,
    onSendDesktopText: (String) -> Unit,
    onSendDesktopKeyCombo: (List<String>) -> Unit,
    onMoveDesktopPointer: (Int, Int) -> Unit,
    onClickDesktopPointer: (Int) -> Unit,
    onScrollDesktopPointer: (Int) -> Unit,
    onSetDesktopVolume: (Int) -> Unit,
    onSetDesktopMicMuted: (Boolean) -> Unit,
    onRefreshSafeWifi: () -> Unit,
    onSelectTrustedDevice: (String?) -> Unit,
    onUnpairDevice: (String) -> Unit,
    onSetDevicePermission: (String, PermissionKey, Boolean) -> Unit,
    onSetNotificationBlocked: (String, String, Boolean) -> Unit,
    onSetAllowPairingOnAllWifi: (Boolean) -> Unit,
    onSetSafeWifiEnabled: (String, Boolean) -> Unit,
    onRequestLocationForSafeWifi: () -> Unit,
    onApproveCameraRequest: () -> Unit,
    onRejectCameraRequest: () -> Unit,
    onStopCameraSession: () -> Unit,
) {
    var pcControlsVisible by rememberSaveable { mutableStateOf(false) }
    var sendFilesVisible by rememberSaveable { mutableStateOf(false) }
    var eventsVisible by rememberSaveable { mutableStateOf(false) }
    var safeWifiVisible by rememberSaveable { mutableStateOf(false) }
    var noticeBlocklistVisible by rememberSaveable { mutableStateOf(false) }
    var notificationFilterDeviceId by rememberSaveable { mutableStateOf<String?>(null) }
    var dismissedPairingCodeKey by rememberSaveable { mutableStateOf("") }
    val selectedTrustedDevice = uiState.selectedDevice
    val awaitingPairingCode = uiState.pairingState as? PairingState.AwaitingCodeEntry
    val pairingCodeKey = awaitingPairingCode?.let { "${it.deviceName}:${it.code}" }.orEmpty()
    LaunchedEffect(pairingCodeKey) {
        if (pairingCodeKey.isNotBlank()) {
            dismissedPairingCodeKey = ""
        }
    }
    if (uiState.cameraSession.hasPendingRequest) {
        CameraRequestDialog(
            cameraSession = uiState.cameraSession,
            onApprove = onApproveCameraRequest,
            onReject = onRejectCameraRequest,
        )
    }
    BackHandler(enabled = safeWifiVisible || noticeBlocklistVisible || notificationFilterDeviceId != null || pcControlsVisible || sendFilesVisible || selectedTrustedDevice != null) {
        safeWifiVisible = false
        noticeBlocklistVisible = false
        notificationFilterDeviceId = null
        pcControlsVisible = false
        sendFilesVisible = false
        onSelectTrustedDevice(null)
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        when {
                            uiState.cameraSession.isActive -> "Camera session"
                            safeWifiVisible -> "Safe Wi-Fi"
                            noticeBlocklistVisible || notificationFilterDeviceId != null -> "Notifications"
                            pcControlsVisible -> "PC Control"
                            sendFilesVisible -> "Send Files"
                            selectedTrustedDevice != null -> selectedTrustedDevice.deviceName
                            else -> "Linkable"
                        },
                    )
                },
                navigationIcon = {
                    if (!uiState.cameraSession.isActive && (safeWifiVisible || noticeBlocklistVisible || notificationFilterDeviceId != null || pcControlsVisible || sendFilesVisible || selectedTrustedDevice != null)) {
                        IconButton(
                            onClick = {
                                safeWifiVisible = false
                                noticeBlocklistVisible = false
                                notificationFilterDeviceId = null
                                pcControlsVisible = false
                                sendFilesVisible = false
                                onSelectTrustedDevice(null)
                            },
                        ) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                actions = {
                    if (!uiState.cameraSession.isActive && !safeWifiVisible && !noticeBlocklistVisible && notificationFilterDeviceId == null && !pcControlsVisible && !sendFilesVisible && selectedTrustedDevice == null) {
                        IconButton(onClick = onRefreshDiscovery) {
                            Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                        }
                    }
                },
            )
        },
    ) { innerPadding ->
        if (uiState.cameraSession.isActive) {
            CameraSessionScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                cameraSession = uiState.cameraSession,
                onStopCameraSession = onStopCameraSession,
            )
            return@Scaffold
        }
        if (safeWifiVisible) {
            SafeWifiScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                safeWifi = uiState.safeWifi,
                onRefresh = onRefreshSafeWifi,
                onSetAllowPairingOnAllWifi = onSetAllowPairingOnAllWifi,
                onSetSafeWifiEnabled = onSetSafeWifiEnabled,
                onRequestLocation = onRequestLocationForSafeWifi,
            )
            return@Scaffold
        }
        if (noticeBlocklistVisible) {
            NoticeBlocklistScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                apps = uiState.installedApps,
                notificationAccessGranted = uiState.notificationAccessGranted,
                onSetNotificationBlocked = { packageName, blocked ->
                    onSetNotificationBlocked("", packageName, blocked)
                },
                onOpenNotificationSettings = onOpenNotificationSettings,
            )
            return@Scaffold
        }
        notificationFilterDeviceId?.let { deviceId ->
            NoticeBlocklistScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                apps = uiState.installedApps,
                notificationAccessGranted = uiState.notificationAccessGranted,
                onSetNotificationBlocked = { packageName, blocked ->
                    onSetNotificationBlocked(deviceId, packageName, blocked)
                },
                onOpenNotificationSettings = onOpenNotificationSettings,
            )
            return@Scaffold
        }
        if (pcControlsVisible) {
            PcControlsScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                onSendDesktopText = onSendDesktopText,
                onSendDesktopKeyCombo = onSendDesktopKeyCombo,
                onMoveDesktopPointer = onMoveDesktopPointer,
                onClickDesktopPointer = onClickDesktopPointer,
                onScrollDesktopPointer = onScrollDesktopPointer,
                onSetDesktopVolume = onSetDesktopVolume,
                onSetDesktopMicMuted = onSetDesktopMicMuted,
            )
            return@Scaffold
        }
        if (sendFilesVisible) {
            SendFilesScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                onSendFileToDesktop = onSendFileToDesktop,
            )
            return@Scaffold
        }
        selectedTrustedDevice?.let { device ->
            TrustedPcDetailScreen(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(16.dp),
                device = device,
                onSetDevicePermission = onSetDevicePermission,
                onOpenPcControls = {
                    onSelectTrustedDevice(null)
                    pcControlsVisible = true
                },
                onOpenSendFiles = {
                    onSetDevicePermission(device.deviceId, PermissionKey.FILES, true)
                    onSelectTrustedDevice(null)
                    sendFilesVisible = true
                },
                onOpenNotificationFilter = {
                    notificationFilterDeviceId = device.deviceId
                    onSelectTrustedDevice(device.deviceId)
                },
            )
            return@Scaffold
        }
        val trustedIds = uiState.trustedDevices.map { it.deviceId }.toSet()
        val scannedUntrustedDevices = uiState.devices.filterNot { device -> device.deviceId in trustedIds }
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                HomeControlRow(
                    isDiscovering = uiState.isDiscovering,
                    safeWifi = uiState.safeWifi,
                    onScanForDesktops = onScanForDesktops,
                    onStopDiscovery = onStopDiscovery,
                    onSetAllowPairingOnAllWifi = onSetAllowPairingOnAllWifi,
                    onRequestLocation = onRequestLocationForSafeWifi,
                )
            }
            if (awaitingPairingCode != null && dismissedPairingCodeKey != pairingCodeKey) {
                item {
                    PairingCodeCard(
                        state = awaitingPairingCode,
                        onDismiss = { dismissedPairingCodeKey = pairingCodeKey },
                    )
                }
            } else if (awaitingPairingCode != null && dismissedPairingCodeKey == pairingCodeKey) {
                item {
                    PairingProgressCard(pairingState = PairingState.PairingInProgress(awaitingPairingCode.deviceName))
                }
            } else if (uiState.pairingState !is PairingState.Idle && uiState.pairingState !is PairingState.Success) {
                item {
                    PairingProgressCard(pairingState = uiState.pairingState)
                }
            }
            item {
                SectionHeader("Connected / Trusted devices")
            }
            if (uiState.trustedDevices.isEmpty()) {
                item {
                    EmptyTrustedDeviceCard()
                }
            } else {
                items(uiState.trustedDevices, key = { it.deviceId }) { trusted ->
                    val matchingScan = uiState.devices.firstOrNull { it.deviceId == trusted.deviceId }
                    TrustedDeviceCard(
                        device = trusted,
                        scannedDevice = matchingScan,
                        onOpenSettings = { onSelectTrustedDevice(trusted.deviceId) },
                        onConnect = onConnect,
                        onUnpairDevice = onUnpairDevice,
                    )
                }
            }
            item {
                SectionHeader("Scanned devices")
            }
            if (scannedUntrustedDevices.isEmpty()) {
                item {
                    EmptyScannedDeviceCard(isDiscovering = uiState.isDiscovering)
                }
            } else {
                items(scannedUntrustedDevices, key = { it.serviceName }) { device ->
                    ScannedDeviceCard(
                        device = device,
                        onConnect = onConnect,
                    )
                }
            }
            item {
                LogsToggleRow(
                    checked = eventsVisible,
                    onCheckedChange = { eventsVisible = it },
                )
            }
            if (eventsVisible) {
                item {
                    DebugLogPanel()
                }
            }
        }
    }
}

@Composable
private fun CameraRequestDialog(
    cameraSession: CameraSessionUiState,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onReject,
        icon = {
            Icon(Icons.Filled.DesktopWindows, contentDescription = null)
        },
        title = {
            Text("Start camera session?")
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("${cameraSession.pendingDesktopName.ifBlank { "A paired desktop" }} wants to use this phone camera.")
                Text(
                    "Route: ${cameraRouteLabel(cameraSession.pendingRoute)}  •  Camera: ${cameraFacingLabel(cameraSession.pendingFacing)}",
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "Requested: ${cameraSession.pendingWidth}x${cameraSession.pendingHeight} @ ${cameraSession.pendingFps} FPS",
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    "The camera starts only after you press Start. Linkable will keep a visible session screen awake until you or the desktop stops it.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        },
        confirmButton = {
            Button(onClick = onApprove) {
                Text("Start camera")
            }
        },
        dismissButton = {
            TextButton(onClick = onReject) {
                Text("Reject")
            }
        },
    )
}

@Composable
private fun CameraSessionScreen(
    modifier: Modifier,
    cameraSession: CameraSessionUiState,
    onStopCameraSession: () -> Unit,
) {
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.DesktopWindows, contentDescription = null, modifier = Modifier.size(30.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Camera is sharing", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                            Text(
                                "Connected to ${cameraSession.activeDesktopName.ifBlank { "desktop" }}",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                    Text(
                        "Keep this screen open. Android keeps camera access reliable while Linkable is visible and running as a camera foreground service.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Button(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = onStopCameraSession,
                    ) {
                        Icon(Icons.Filled.Stop, contentDescription = null, modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Stop camera")
                    }
                }
            }
        }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Session details", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    CameraInfoRow("Route", cameraRouteLabel(cameraSession.activeRoute))
                    CameraInfoRow("Camera", cameraFacingLabel(cameraSession.activeFacing))
                    CameraInfoRow("Stream", "${cameraSession.activeWidth}x${cameraSession.activeHeight} @ ${cameraSession.activeFps} FPS")
                    CameraInfoRow("Frames sent", cameraSession.framesSent.toString())
                    CameraInfoRow("Status", cameraSession.detail)
                }
            }
        }
    }
}

@Composable
private fun CameraInfoRow(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        Text(label, modifier = Modifier.weight(0.38f), style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
        Text(value, modifier = Modifier.weight(0.62f), style = MaterialTheme.typography.bodySmall)
    }
}

private fun cameraRouteLabel(route: CameraRoute): String {
    return when (route) {
        CameraRoute.CAMERA_ROUTE_USB -> "USB"
        CameraRoute.CAMERA_ROUTE_LAN -> "LAN"
        else -> "Unknown"
    }
}

private fun cameraFacingLabel(facing: CameraFacing): String {
    return when (facing) {
        CameraFacing.CAMERA_FACING_FRONT -> "Front"
        CameraFacing.CAMERA_FACING_BACK -> "Back"
        else -> "Default"
    }
}

@Composable
private fun PairingCodeCard(
    state: PairingState.AwaitingCodeEntry,
    onDismiss: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Security, contentDescription = null, modifier = Modifier.size(28.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("Pairing code for ${state.deviceName}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text("Enter this code on the desktop prompt. Tap OK after you have read it.", style = MaterialTheme.typography.bodyMedium)
                }
            }
            Text(
                text = state.code.chunked(3).joinToString(" "),
                style = MaterialTheme.typography.displayLarge.copy(
                    fontSize = 54.sp,
                    letterSpacing = 4.sp,
                ),
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSecondaryContainer,
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = onDismiss,
                modifier = Modifier.align(Alignment.End),
            ) {
                Text("OK")
            }
        }
    }
}

@Composable
private fun PairingProgressCard(pairingState: PairingState) {
    val message = when (pairingState) {
        is PairingState.Connecting -> "Opening secure LAN session with ${pairingState.deviceName}."
        is PairingState.PairingInProgress -> "Waiting for desktop confirmation from ${pairingState.deviceName}."
        is PairingState.Reconnecting -> "Restoring ${pairingState.deviceName}; attempt ${pairingState.attempt}. ${pairingState.detail}"
        is PairingState.Error -> pairingState.message
        is PairingState.AwaitingCodeEntry,
        PairingState.Idle,
        is PairingState.Success -> ""
    }
    if (message.isBlank()) return
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Filled.Link, contentDescription = null, modifier = Modifier.size(24.dp))
            Text(message, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun HomeControlRow(
    isDiscovering: Boolean,
    safeWifi: SafeWifiUiState,
    onScanForDesktops: () -> Unit,
    onStopDiscovery: () -> Unit,
    onSetAllowPairingOnAllWifi: (Boolean) -> Unit,
    onRequestLocation: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        FilledTonalButton(
            modifier = Modifier.height(46.dp),
            onClick = if (isDiscovering) onStopDiscovery else onScanForDesktops,
        ) {
            Icon(
                if (isDiscovering) Icons.Filled.Stop else Icons.Filled.Search,
                contentDescription = null,
                modifier = Modifier.size(22.dp),
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(if (isDiscovering) "Scanning" else "Scan 30s")
        }
        Card(
            modifier = Modifier
                .weight(1f)
                .height(46.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Wi-Fi Access",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    if (safeWifi.allowAllWifi) "All" else "Safe",
                    style = MaterialTheme.typography.bodySmall,
                )
                Switch(
                    checked = safeWifi.allowAllWifi,
                    onCheckedChange = { allowAll ->
                        if (!allowAll && !safeWifi.locationPermissionGranted) {
                            onRequestLocation()
                        } else {
                            onSetAllowPairingOnAllWifi(allowAll)
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
    )
}

@Composable
private fun EmptyTrustedDeviceCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Text(
            "No trusted desktop yet. Scan and request a connection from a discovered PC.",
            modifier = Modifier.padding(14.dp),
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun EmptyScannedDeviceCard(isDiscovering: Boolean) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(
                if (isDiscovering) Icons.Filled.Search else Icons.Filled.WifiOff,
                contentDescription = null,
                modifier = Modifier.size(22.dp),
            )
            Text(
                if (isDiscovering) "Scanning for broadcasting PCs..." else "No scanned PCs. Tap Scan 30s.",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun TrustedDeviceCard(
    device: TrustedDeviceUiState,
    scannedDevice: DiscoveredDevice?,
    onOpenSettings: () -> Unit,
    onConnect: (DiscoveredDevice) -> Unit,
    onUnpairDevice: (String) -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpenSettings),
        colors = CardDefaults.cardColors(
            containerColor = if (device.connected) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
        ),
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DeviceConnectionIcon(
                    lanConnected = device.connected,
                    bluetoothConnected = device.bluetoothConnected,
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text(device.deviceName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(device.deviceId, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                if (!device.connected && scannedDevice != null) {
                    IconButton(onClick = { onConnect(scannedDevice) }) {
                        Icon(Icons.Filled.Link, contentDescription = "Request pairing")
                    }
                } else {
                    IconButton(onClick = { onUnpairDevice(device.deviceId) }) {
                        Icon(Icons.Filled.Delete, contentDescription = "Unpair")
                    }
                }
            }
            Text(
                text = when {
                    device.connected && device.bluetoothConnected -> "LAN + Bluetooth connected"
                    device.connected -> "LAN connected"
                    scannedDevice != null -> "Available on LAN"
                    else -> "Unavailable"
                },
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun DeviceConnectionIcon(lanConnected: Boolean, bluetoothConnected: Boolean) {
    Box(modifier = Modifier.size(38.dp)) {
        Icon(
            imageVector = if (lanConnected) Icons.Filled.Wifi else Icons.Filled.WifiOff,
            contentDescription = null,
            tint = if (lanConnected) Color(0xFF1B8F3A) else MaterialTheme.colorScheme.outline,
            modifier = Modifier.size(30.dp),
        )
        if (lanConnected && bluetoothConnected) {
            Icon(
                imageVector = Icons.Filled.Bluetooth,
                contentDescription = null,
                tint = Color(0xFF1B8F3A),
                modifier = Modifier
                    .size(18.dp)
                    .align(androidx.compose.ui.Alignment.BottomEnd),
            )
        }
    }
}

@Composable
private fun ScannedDeviceCard(device: DiscoveredDevice, onConnect: (DiscoveredDevice) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(Icons.Filled.Wifi, contentDescription = null, tint = Color(0xFF1B8F3A), modifier = Modifier.size(26.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(device.deviceName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Text(device.endpoint, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            IconButton(onClick = { onConnect(device) }) {
                Icon(Icons.Filled.Link, contentDescription = "Request connection")
            }
        }
    }
}

@Composable
private fun LogsToggleRow(checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(Icons.Filled.BugReport, contentDescription = null, modifier = Modifier.size(22.dp))
            Text("Logs", modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
            Switch(checked = checked, onCheckedChange = onCheckedChange)
        }
    }
}

@Composable
private fun CopyAllLogsButton(debugEvents: List<DebugEvent>) {
    val clipboard = LocalClipboardManager.current
    Button(
        onClick = {
            clipboard.setText(
                AnnotatedString(
                    debugEvents.joinToString("\n") { event ->
                        "${event.timestampMs} ${event.category}: ${event.message}"
                    },
                ),
            )
        },
        modifier = Modifier.fillMaxWidth(),
        enabled = debugEvents.isNotEmpty(),
    ) {
        Icon(Icons.Filled.ContentPaste, contentDescription = null, modifier = Modifier.size(20.dp))
        Spacer(modifier = Modifier.width(8.dp))
        Text("Copy all logs")
    }
}

@Composable
private fun DebugLogPanel() {
    val debugEvents by DebugEventLog.events.collectAsState()
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        CopyAllLogsButton(debugEvents)
        debugEvents.takeLast(20).asReversed().forEach { event ->
            LogEventRow(event)
        }
    }
}

@Composable
private fun LogEventRow(event: DebugEvent) {
    SelectionContainer {
        Text(
            text = "${event.timestampMs} ${event.category}: ${event.message}",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun SafeWifiScreen(
    modifier: Modifier,
    safeWifi: SafeWifiUiState,
    onRefresh: () -> Unit,
    onSetAllowPairingOnAllWifi: (Boolean) -> Unit,
    onSetSafeWifiEnabled: (String, Boolean) -> Unit,
    onRequestLocation: () -> Unit,
) {
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            SafeWifiCard(
                safeWifi = safeWifi,
                onRefresh = onRefresh,
                onSetAllowPairingOnAllWifi = onSetAllowPairingOnAllWifi,
                onSetSafeWifiEnabled = onSetSafeWifiEnabled,
                onRequestLocation = onRequestLocation,
            )
        }
    }
}

@Composable
private fun NoticeBlocklistScreen(
    modifier: Modifier,
    apps: List<InstalledApp>,
    notificationAccessGranted: Boolean,
    onSetNotificationBlocked: (String, Boolean) -> Unit,
    onOpenNotificationSettings: () -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    val filteredApps = apps.filter { app ->
        query.isBlank() ||
            app.label.contains(query, ignoreCase = true) ||
            app.packageName.contains(query, ignoreCase = true)
    }
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (!notificationAccessGranted) {
            item {
                NotificationAccessWarningCard(onOpenNotificationSettings = onOpenNotificationSettings)
            }
        }
        item {
            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = query,
                onValueChange = { query = it },
                label = { Text("Search apps") },
                singleLine = true,
            )
        }
        items(filteredApps, key = { it.packageName }) { app ->
            NoticeBlocklistRow(
                app = app,
                onSetNotificationBlocked = onSetNotificationBlocked,
            )
        }
    }
}

@Composable
private fun NoticeBlocklistRow(
    app: InstalledApp,
    onSetNotificationBlocked: (String, Boolean) -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(app.label, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
                Text(app.packageName, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column {
                Text("Forward", style = MaterialTheme.typography.bodySmall)
                Switch(
                    checked = !app.notificationBlocked,
                    onCheckedChange = { forward -> onSetNotificationBlocked(app.packageName, !forward) },
                )
            }
        }
    }
}

@Composable
private fun NotificationAccessWarningCard(onOpenNotificationSettings: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Filled.Warning, contentDescription = null)
                Column(modifier = Modifier.weight(1f)) {
                    Text("Notification access required", fontWeight = FontWeight.SemiBold)
                    Text(
                        "Grant notification read, reply, and control access so Linkable can forward notices to the desktop.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            Button(onClick = onOpenNotificationSettings, modifier = Modifier.fillMaxWidth()) {
                Text("Open notification access")
            }
        }
    }
}

@Composable
private fun TrustedPcDetailScreen(
    modifier: Modifier,
    device: TrustedDeviceUiState,
    onSetDevicePermission: (String, PermissionKey, Boolean) -> Unit,
    onOpenPcControls: () -> Unit,
    onOpenSendFiles: () -> Unit,
    onOpenNotificationFilter: () -> Unit,
) {
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            DevicePermissionCard(
                device = device,
                onSetDevicePermission = onSetDevicePermission,
                onOpenPcControls = onOpenPcControls,
                onOpenSendFiles = onOpenSendFiles,
                onOpenNotificationFilter = onOpenNotificationFilter,
            )
        }
    }
}

@Composable
private fun DevicePermissionCard(
    device: TrustedDeviceUiState,
    onSetDevicePermission: (String, PermissionKey, Boolean) -> Unit,
    onOpenPcControls: () -> Unit,
    onOpenSendFiles: () -> Unit,
    onOpenNotificationFilter: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DeviceConnectionIcon(device.connected, device.bluetoothConnected)
                Column(modifier = Modifier.weight(1f)) {
                    Text(device.deviceName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text("Device settings", style = MaterialTheme.typography.bodySmall)
                }
            }
            PermissionToggle(
                icon = Icons.Filled.Notifications,
                label = "Allow notifications",
                checked = device.permissions.notifications,
            ) {
                onSetDevicePermission(device.deviceId, PermissionKey.NOTIFICATIONS, it)
            }
            PermissionToggle(
                icon = Icons.Filled.Call,
                label = "Allow calls & contacts",
                checked = device.permissions.calls && device.permissions.contacts,
            ) { enabled ->
                onSetDevicePermission(device.deviceId, PermissionKey.CALLS, enabled)
                onSetDevicePermission(device.deviceId, PermissionKey.CONTACTS, enabled)
            }
            PermissionToggle(
                icon = Icons.Filled.Folder,
                label = "Allow file transfer & browsing",
                checked = device.permissions.files && device.permissions.fileBrowse,
            ) { enabled ->
                onSetDevicePermission(device.deviceId, PermissionKey.FILES, enabled)
                onSetDevicePermission(device.deviceId, PermissionKey.FILE_BROWSE, enabled)
            }
            PermissionToggle(
                icon = Icons.Filled.ContentPaste,
                label = "Forward clipboard to PC",
                checked = device.permissions.forwardClipboardToPc,
            ) {
                onSetDevicePermission(device.deviceId, PermissionKey.FORWARD_CLIPBOARD_TO_PC, it)
            }
            Text("Actions", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                DeviceActionButton(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Filled.Keyboard,
                    label = "PC Control",
                    onClick = onOpenPcControls,
                )
                DeviceActionButton(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Filled.Folder,
                    label = "Send Files",
                    onClick = onOpenSendFiles,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                DeviceActionButton(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Filled.NotificationsOff,
                    label = "Notifications",
                    onClick = onOpenNotificationFilter,
                )
            }
        }
    }
}

@Composable
private fun DeviceActionButton(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
) {
    FilledTonalButton(
        modifier = modifier.height(48.dp),
        onClick = onClick,
    ) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
        Spacer(modifier = Modifier.width(8.dp))
        Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun PermissionToggle(
    icon: ImageVector,
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(22.dp))
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun SendFilesScreen(
    modifier: Modifier,
    onSendFileToDesktop: () -> Unit,
) {
    val debugEvents by DebugEventLog.events.collectAsState()
    val transferEvents = debugEvents.filter { it.category == "transfer" }.takeLast(5).asReversed()
    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = null, modifier = Modifier.size(24.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Send files to PC", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            Text("Choose a file from this phone and queue it for the connected desktop.", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    Button(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = onSendFileToDesktop,
                    ) {
                        Icon(Icons.Filled.Folder, contentDescription = null, modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Choose file")
                    }
                }
            }
        }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Transfer status", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    if (transferEvents.isEmpty()) {
                        Text("No file transfer events yet.", style = MaterialTheme.typography.bodyMedium)
                    } else {
                        transferEvents.forEach { event ->
                            Text(
                                text = event.message,
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                    Text(
                        "Received PC files are also announced through Android notifications and saved under Linkable/Downloads when available.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
    }
}

@Composable
private fun SafeWifiCard(
    safeWifi: SafeWifiUiState,
    onRefresh: () -> Unit,
    onSetAllowPairingOnAllWifi: (Boolean) -> Unit,
    onSetSafeWifiEnabled: (String, Boolean) -> Unit,
    onRequestLocation: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Filled.Security, contentDescription = null)
                Column(modifier = Modifier.weight(1f)) {
                    Text("Safe Wi-Fi", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(
                        "Default mode allows pairing and reconnect on all Wi-Fi. Turn it off to restrict Linkable to selected Wi-Fi networks.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                TextButton(onClick = onRefresh) {
                    Text("Refresh")
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                Text("Allow pairing on all Wi-Fi", modifier = Modifier.weight(1f))
                Switch(
                    checked = safeWifi.allowAllWifi,
                    onCheckedChange = { allowAll ->
                        if (!allowAll && !safeWifi.locationPermissionGranted) {
                            onRequestLocation()
                        } else {
                            onSetAllowPairingOnAllWifi(allowAll)
                        }
                    },
                )
            }
            if (!safeWifi.allowAllWifi) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Filled.LocationOn, contentDescription = null, modifier = Modifier.size(18.dp))
                    Text(
                        if (safeWifi.locationPermissionGranted) {
                            "Current Wi-Fi: ${safeWifi.currentWifiLabel.ifBlank { "unavailable" }}"
                        } else {
                            "Location permission is needed only for strict Safe Wi-Fi mode."
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                if (!safeWifi.locationPermissionGranted) {
                    Button(onClick = onRequestLocation, modifier = Modifier.fillMaxWidth()) {
                        Text("Grant Location")
                    }
                }
                if (safeWifi.networks.isEmpty()) {
                    Text("No safe Wi-Fi networks recorded yet.", style = MaterialTheme.typography.bodySmall)
                } else {
                    safeWifi.networks.forEach { network ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                            Text(network.label, modifier = Modifier.weight(1f))
                            Switch(
                                checked = network.enabled,
                                onCheckedChange = { enabled -> onSetSafeWifiEnabled(network.fingerprint, enabled) },
                            )
                        }
                    }
                }
            }
            if (safeWifi.detail.isNotBlank()) {
                Text(safeWifi.detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

/**
 * Full-screen control surface that turns the phone into a PC touchpad, live keyboard, and audio toggle panel.
 */
@Composable
private fun PcControlsScreen(
    modifier: Modifier,
    onSendDesktopText: (String) -> Unit,
    onSendDesktopKeyCombo: (List<String>) -> Unit,
    onMoveDesktopPointer: (Int, Int) -> Unit,
    onClickDesktopPointer: (Int) -> Unit,
    onScrollDesktopPointer: (Int) -> Unit,
    onSetDesktopVolume: (Int) -> Unit,
    onSetDesktopMicMuted: (Boolean) -> Unit,
) {
    var keyboardVisible by rememberSaveable { mutableStateOf(false) }
    var keyboardText by rememberSaveable { mutableStateOf("") }
    var volume by rememberSaveable { mutableFloatStateOf(70f) }
    var speakerMuted by rememberSaveable { mutableStateOf(false) }
    var micMuted by rememberSaveable { mutableStateOf(false) }
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current
    LaunchedEffect(keyboardVisible) {
        if (keyboardVisible) {
            focusRequester.requestFocus()
            keyboardController?.show()
        }
    }
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        TouchpadSurface(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            onMoveDesktopPointer = onMoveDesktopPointer,
            onScrollDesktopPointer = onScrollDesktopPointer,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            Button(modifier = Modifier.weight(1f).height(54.dp), onClick = { onClickDesktopPointer(1) }) {
                Text("Left click")
            }
            Button(modifier = Modifier.weight(1f).height(54.dp), onClick = { onClickDesktopPointer(3) }) {
                Text("Right click")
            }
        }
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    FilledTonalButton(
                        modifier = Modifier.weight(1f),
                        onClick = {
                            speakerMuted = !speakerMuted
                            onSetDesktopVolume(if (speakerMuted) 0 else volume.toInt())
                        },
                    ) {
                        Icon(Icons.AutoMirrored.Filled.VolumeOff, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(if (speakerMuted) "Unmute" else "Mute")
                    }
                    FilledTonalButton(
                        modifier = Modifier.weight(1f),
                        onClick = {
                            micMuted = !micMuted
                            onSetDesktopMicMuted(micMuted)
                        },
                    ) {
                        Icon(Icons.Filled.MicOff, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(if (micMuted) "Mic on" else "Mic mute")
                    }
                }
                Text("Speaker ${volume.toInt()}%", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
                Slider(
                    value = volume,
                    onValueChange = { value ->
                        volume = value
                        speakerMuted = false
                    },
                    onValueChangeFinished = { onSetDesktopVolume(volume.toInt()) },
                    valueRange = 0f..100f,
                )
            }
        }
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    FilledTonalButton(onClick = { keyboardVisible = !keyboardVisible }) {
                        Icon(Icons.Filled.Keyboard, contentDescription = "Keyboard", modifier = Modifier.size(20.dp))
                    }
                    Text(
                        text = "Live keyboard",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                if (keyboardVisible) {
                    OutlinedTextField(
                        modifier = Modifier
                            .fillMaxWidth()
                            .focusRequester(focusRequester),
                        value = keyboardText,
                        onValueChange = { next ->
                            streamKeyboardChange(
                                previous = keyboardText,
                                next = next,
                                onSendDesktopText = onSendDesktopText,
                                onSendDesktopKeyCombo = onSendDesktopKeyCombo,
                            )
                            keyboardText = next
                        },
                        label = { Text("Type to PC") },
                        singleLine = true,
                    )
                }
            }
        }
    }
}

/**
 * Gesture capture area for relative pointer movement and two-finger scroll events forwarded to the paired PC.
 */
@Composable
private fun TouchpadSurface(
    modifier: Modifier,
    onMoveDesktopPointer: (Int, Int) -> Unit,
    onScrollDesktopPointer: (Int) -> Unit,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(10.dp)
                .pointerInput(Unit) {
                    awaitPointerEventScope {
                        while (true) {
                            val event = awaitPointerEvent()
                            val pressed = event.changes.filter { it.pressed }
                            when {
                                pressed.size >= 2 -> {
                                    val averageDy = pressed.map { it.positionChange().y }.average()
                                    if (abs(averageDy) >= 2.0) {
                                        val scroll = (-averageDy / 8.0).roundToInt().coerceIn(-6, 6)
                                        if (scroll != 0) onScrollDesktopPointer(scroll)
                                    }
                                    pressed.forEach { it.consume() }
                                }

                                pressed.size == 1 -> {
                                    val change = pressed.first()
                                    val delta = change.positionChange()
                                    if (abs(delta.x) >= 0.5f || abs(delta.y) >= 0.5f) {
                                        val dx = (delta.x * 1.35f).roundToInt().coerceIn(-80, 80)
                                        val dy = (delta.y * 1.35f).roundToInt().coerceIn(-80, 80)
                                        if (dx != 0 || dy != 0) onMoveDesktopPointer(dx, dy)
                                    }
                                    change.consume()
                                }
                            }
                        }
                    }
                },
        ) {
            Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
            ) {
                Icon(
                    Icons.Filled.Mouse,
                    contentDescription = null,
                    modifier = Modifier
                        .size(44.dp)
                        .padding(bottom = 8.dp),
                    tint = MaterialTheme.colorScheme.primary,
                )
                Text("Touchpad", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text("One finger moves pointer. Two fingers scroll.", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

private fun streamKeyboardChange(
    previous: String,
    next: String,
    onSendDesktopText: (String) -> Unit,
    onSendDesktopKeyCombo: (List<String>) -> Unit,
) {
    when {
        next.length > previous.length && next.startsWith(previous) -> {
            onSendDesktopText(next.removePrefix(previous))
        }

        next.length < previous.length && previous.startsWith(next) -> {
            repeat(previous.length - next.length) {
                onSendDesktopKeyCombo(listOf("backspace"))
            }
        }

        next != previous && next.isNotBlank() -> {
            onSendDesktopText(next)
        }
    }
}
