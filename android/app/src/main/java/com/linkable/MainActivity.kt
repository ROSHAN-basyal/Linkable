package com.linkable

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.view.WindowManager
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.linkable.service.LinkableForegroundService
import com.linkable.ui.DiscoveryViewModel
import com.linkable.ui.screens.DiscoveryScreen
import com.linkable.ui.theme.LinkableTheme

class MainActivity : ComponentActivity() {
    private var discoveryViewModel: com.linkable.ui.DiscoveryViewModel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sendFilePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                handlePickedSendFile(result.data)
            }
        }
        val fallbackSendFilePicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            if (uri != null) {
                queuePickedSendFile(uri, persistable = false)
            }
        }
        val safeWifiLocationPermission = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
            val locationGranted =
                grants[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
                    grants[Manifest.permission.ACCESS_COARSE_LOCATION] == true
            if (locationGranted) {
                discoveryViewModel?.setAllowPairingOnAllWifi(false)
            } else {
                discoveryViewModel?.refreshSafeWifi()
            }
        }
        enableEdgeToEdge()
        requestNotificationPermissionIfNeeded()
        requestPhoneStatePermissionIfNeeded()
        requestAnswerCallsPermissionIfNeeded()
        requestCallPhonePermissionIfNeeded()
        requestBluetoothPermissionsIfNeeded()
        requestLegacyStoragePermissionIfNeeded()
        requestCameraPermissionIfNeeded()
        LinkableForegroundService.start(this)
        setContent {
            LinkableTheme {
                val viewModel: DiscoveryViewModel = viewModel()
                discoveryViewModel = viewModel
                val uiState by viewModel.uiState.collectAsStateWithLifecycle()
                DisposableEffect(uiState.cameraSession.keepScreenAwake) {
                    if (uiState.cameraSession.keepScreenAwake) {
                        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    } else {
                        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    }
                    onDispose {
                        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    }
                }
                DiscoveryScreen(
                    uiState = uiState,
                    onStopDiscovery = viewModel::stopDiscovery,
                    onRefreshDiscovery = viewModel::refreshDiscovery,
                    onScanForDesktops = viewModel::scanForDesktops,
                    onConnect = viewModel::startPairing,
                    onOpenNotificationSettings = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                    onSendFileToDesktop = {
                        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                            addCategory(Intent.CATEGORY_OPENABLE)
                            type = "*/*"
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
                        }
                        runCatching {
                            sendFilePicker.launch(intent)
                        }.onFailure {
                            fallbackSendFilePicker.launch("*/*")
                        }
                    },
                    onSendDesktopText = viewModel::sendDesktopText,
                    onSendDesktopKeyCombo = viewModel::sendDesktopKeyCombo,
                    onMoveDesktopPointer = viewModel::moveDesktopPointer,
                    onClickDesktopPointer = viewModel::clickDesktopPointer,
                    onScrollDesktopPointer = viewModel::scrollDesktopPointer,
                    onSetDesktopVolume = viewModel::setDesktopVolume,
                    onSetDesktopMicMuted = viewModel::setDesktopMicMuted,
                    onRefreshSafeWifi = viewModel::refreshSafeWifi,
                    onSelectTrustedDevice = viewModel::selectTrustedDevice,
                    onUnpairDevice = viewModel::unpairDevice,
                    onSetDevicePermission = { deviceId, key, enabled ->
                        if (enabled && key == com.linkable.trust.PermissionKey.CALLS) {
                            requestPhoneStatePermissionIfNeeded()
                            requestAnswerCallsPermissionIfNeeded()
                            requestCallPhonePermissionIfNeeded()
                            requestCallLogPermissionIfNeeded()
                        }
                        if (enabled && key == com.linkable.trust.PermissionKey.CONTACTS) {
                            requestContactsPermissionIfNeeded()
                            requestCallLogPermissionIfNeeded()
                        }
                        if (enabled && key == com.linkable.trust.PermissionKey.FILE_BROWSE) {
                            requestBroadStorageAccessIfNeeded()
                        }
                        viewModel.setDevicePermission(deviceId, key, enabled)
                    },
                    onSetNotificationBlocked = viewModel::setNotificationBlocked,
                    onSetAllowPairingOnAllWifi = { allowAll ->
                        if (!allowAll && checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                            safeWifiLocationPermission.launch(locationPermissions())
                        } else {
                            viewModel.setAllowPairingOnAllWifi(allowAll)
                        }
                    },
                    onSetSafeWifiEnabled = viewModel::setSafeWifiEnabled,
                    onRequestLocationForSafeWifi = {
                        safeWifiLocationPermission.launch(locationPermissions())
                    },
                    onApproveCameraRequest = {
                        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                            requestCameraPermissionIfNeeded()
                        } else {
                            viewModel.approvePendingCameraRequest()
                        }
                    },
                    onRejectCameraRequest = viewModel::rejectPendingCameraRequest,
                    onStopCameraSession = viewModel::stopCameraFromPhone,
                )
            }
        }
    }

    private fun handlePickedSendFile(intent: Intent?) {
        if (intent == null) return
        val clipData = intent.clipData
        if (clipData != null && clipData.itemCount > 0) {
            for (index in 0 until clipData.itemCount) {
                queuePickedSendFile(
                    uri = clipData.getItemAt(index).uri,
                    persistable = intent.flags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION != 0,
                )
            }
            return
        }
        intent.data?.let { uri ->
            queuePickedSendFile(
                uri = uri,
                persistable = intent.flags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION != 0,
            )
        }
    }

    private fun queuePickedSendFile(uri: Uri, persistable: Boolean) {
        if (persistable) {
            runCatching {
                contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
        }
        discoveryViewModel?.sendFileToDesktop(uri)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_CAMERA_PERMISSION &&
            grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        ) {
            discoveryViewModel?.refreshPermissions()
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestRuntimePermissionsIfMissing(
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                REQUEST_NOTIFICATION_PERMISSION,
            )
        }
    }

    private fun requestLegacyStoragePermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            requestRuntimePermissionsIfMissing(
                arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE),
                REQUEST_STORAGE_PERMISSION,
            )
        }
        if (Build.VERSION.SDK_INT in Build.VERSION_CODES.Q..Build.VERSION_CODES.S_V2) {
            requestRuntimePermissionsIfMissing(
                arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE),
                REQUEST_STORAGE_PERMISSION,
            )
        }
    }

    private fun requestBroadStorageAccessIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager()) return
        runCatching {
            startActivity(
                Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                    data = Uri.parse("package:$packageName")
                },
            )
        }.onFailure {
            startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
        }
    }

    private fun requestPhoneStatePermissionIfNeeded() {
        requestRuntimePermissionsIfMissing(arrayOf(Manifest.permission.READ_PHONE_STATE), REQUEST_PHONE_STATE_PERMISSION)
    }

    private fun requestAnswerCallsPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            checkSelfPermission(Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.ANSWER_PHONE_CALLS), REQUEST_ANSWER_CALLS_PERMISSION)
        }
    }

    private fun requestCallPhonePermissionIfNeeded() {
        requestRuntimePermissionsIfMissing(arrayOf(Manifest.permission.CALL_PHONE), REQUEST_CALL_PHONE_PERMISSION)
    }

    private fun requestContactsPermissionIfNeeded() {
        requestRuntimePermissionsIfMissing(arrayOf(Manifest.permission.READ_CONTACTS), REQUEST_CONTACTS_PERMISSION)
    }

    private fun requestCallLogPermissionIfNeeded() {
        requestRuntimePermissionsIfMissing(arrayOf(Manifest.permission.READ_CALL_LOG), REQUEST_CALL_LOG_PERMISSION)
    }

    private fun requestBluetoothPermissionsIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val permissions = arrayOf(
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_SCAN,
            ).filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
            if (permissions.isNotEmpty()) {
                requestPermissions(permissions.toTypedArray(), REQUEST_BLUETOOTH_PERMISSION)
            }
        }
    }

    private fun requestCameraPermissionIfNeeded() {
        requestRuntimePermissionsIfMissing(arrayOf(Manifest.permission.CAMERA), REQUEST_CAMERA_PERMISSION)
    }

    private fun requestLocationPermissionIfNeeded() {
        requestRuntimePermissionsIfMissing(
            locationPermissions(),
            REQUEST_LOCATION_PERMISSION,
        )
    }

    private fun locationPermissions(): Array<String> = arrayOf(
        Manifest.permission.ACCESS_COARSE_LOCATION,
        Manifest.permission.ACCESS_FINE_LOCATION,
    )

    private fun requestRuntimePermissionsIfMissing(permissions: Array<String>, requestCode: Int) {
        val missing = permissions.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            requestPermissions(missing.toTypedArray(), requestCode)
        }
    }

    companion object {
        private const val REQUEST_NOTIFICATION_PERMISSION = 4101
        private const val REQUEST_STORAGE_PERMISSION = 4102
        private const val REQUEST_PHONE_STATE_PERMISSION = 4103
        private const val REQUEST_ANSWER_CALLS_PERMISSION = 4104
        private const val REQUEST_CALL_PHONE_PERMISSION = 4105
        private const val REQUEST_BLUETOOTH_PERMISSION = 4106
        private const val REQUEST_LOCATION_PERMISSION = 4107
        private const val REQUEST_CONTACTS_PERMISSION = 4108
        private const val REQUEST_CALL_LOG_PERMISSION = 4109
        private const val REQUEST_CAMERA_PERMISSION = 4110
    }
}
