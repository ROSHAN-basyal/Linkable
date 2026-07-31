package com.linkable.pairing

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import com.linkable.MainActivity
import com.linkable.apps.InstalledAppsProvider
import com.linkable.bluetooth.BluetoothAssistHandler
import com.linkable.camera.CameraStreamController
import com.linkable.camera.CameraStreamingService
import com.linkable.clipboard.PhoneClipboardMonitor
import com.linkable.calls.CallControlHandler
import com.linkable.calls.CallStateBridge
import com.linkable.calls.CallStateMonitor
import com.linkable.calls.DialHandler
import com.linkable.calls.TelephonyDiagnosticsProvider
import com.linkable.contacts.PhoneContactsProvider
import com.linkable.crypto.CryptoUtils
import com.linkable.crypto.DeviceIdentity
import com.linkable.crypto.EphemeralKeyPair
import com.linkable.crypto.SessionCipher
import com.linkable.debug.DebugEventLog
import com.linkable.discovery.DiscoveredDevice
import com.linkable.discovery.DiscoverySource
import com.linkable.network.SafeNetworkStore
import com.linkable.notifications.NotificationActionStore
import com.linkable.notifications.NotificationBlocklistStore
import com.linkable.notifications.NotificationBridge
import com.linkable.notifications.PhoneNotificationEvent
import com.linkable.protocol.v1.CapabilitiesRequest
import com.linkable.protocol.v1.CapabilitiesResponse
import com.linkable.protocol.v1.CameraStreamStartResult
import com.linkable.protocol.v1.DeviceInfoRequest
import com.linkable.protocol.v1.DeviceInfoResponse
import com.linkable.protocol.v1.DesktopInputRequest
import com.linkable.protocol.v1.DesktopInputResult
import com.linkable.protocol.v1.DeviceId
import com.linkable.protocol.v1.Heartbeat
import com.linkable.protocol.v1.PacketType
import com.linkable.protocol.v1.PairingChallenge
import com.linkable.protocol.v1.PairingComplete
import com.linkable.protocol.v1.PairingConfirm
import com.linkable.protocol.v1.PairingReject
import com.linkable.protocol.v1.PairingRequest
import com.linkable.protocol.v1.PeerDescriptor
import com.linkable.protocol.v1.Ping
import com.linkable.protocol.v1.Pong
import com.linkable.protocol.v1.ProtocolVersion
import com.linkable.protocol.v1.Role
import com.linkable.protocol.v1.SessionAck
import com.linkable.protocol.v1.SessionClose
import com.linkable.protocol.v1.SessionCloseReason
import com.linkable.protocol.v1.SessionInit
import com.linkable.protocol.v1.SharedAppsSnapshot
import com.linkable.protocol.v1.Timestamp
import com.linkable.storage.PhoneStorageBrowser
import com.linkable.transport.ConnectionIO
import com.linkable.transport.EncryptedConnection
import com.linkable.transport.SessionEventSignal
import com.linkable.transfer.FileTransferReceiver
import com.linkable.transfer.PhoneFileSender
import com.linkable.trust.TrustedDevice
import com.linkable.trust.DevicePermissionStore
import com.linkable.trust.TrustStore
import com.linkable.utilities.PhoneRinger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.net.InetSocketAddress
import java.net.Socket
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong


private data class PendingPairingSession(
    val device: DiscoveredDevice,
    val socket: Socket,
    val io: ConnectionIO,
    val request: PairingRequest,
    val challenge: PairingChallenge,
    val code: String,
)


class PairingManager(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val identity = DeviceIdentity(alias = "linkable_identity", deviceName = Build.MODEL ?: "Android Phone")
    private val trustStore = TrustStore(appContext)
    private val devicePermissionStore = DevicePermissionStore(appContext)
    private val safeNetworkStore = SafeNetworkStore(appContext)
    private val wifiManager = appContext.getSystemService(WifiManager::class.java)
    private val fileTransferReceiver = FileTransferReceiver(appContext)
    private val phoneFileSender = PhoneFileSender(appContext)
    private val installedAppsProvider = InstalledAppsProvider(appContext)
    private val notificationBlocklistStore = NotificationBlocklistStore(appContext)
    private val storageBrowser = PhoneStorageBrowser()
    private val phoneRinger = PhoneRinger(appContext)
    private val bluetoothAssistHandler = BluetoothAssistHandler(appContext)
    private val callControlHandler = CallControlHandler(appContext)
    private val callStateMonitor = CallStateMonitor(appContext)
    private val dialHandler = DialHandler(appContext)
    private val telephonyDiagnosticsProvider = TelephonyDiagnosticsProvider(appContext)
    private val phoneContactsProvider = PhoneContactsProvider(appContext)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _state = MutableStateFlow<PairingState>(PairingState.Idle)
    private val sequenceCounter = AtomicLong(1)
    private val outboundFiles = Channel<Uri>(Channel.BUFFERED)
    private val outboundDesktopInput = Channel<DesktopInputRequest>(Channel.BUFFERED)
    private val outboundCameraStartResults = Channel<CameraStreamStartResult>(Channel.BUFFERED)
    private val connectionAttemptInFlight = AtomicBoolean(false)
    private val pairingConfirmationInFlight = AtomicBoolean(false)
    @Volatile
    private var pendingSession: PendingPairingSession? = null
    @Volatile
    private var activeSessionJob: Job? = null
    @Volatile
    private var activeSocket: Socket? = null
    @Volatile
    private var connectingSocket: Socket? = null
    private val lastAutoConnectAttemptAt = ConcurrentHashMap<String, Long>()
    private val lastPermissionDropLogAt = ConcurrentHashMap<String, Long>()

    val state: StateFlow<PairingState> = _state.asStateFlow()

    fun trustedDevices() = trustStore.listRecords()

    fun hasTrustedDevices(): Boolean = trustStore.listRecords().isNotEmpty()

    fun onDevicePermissionsChanged(deviceId: String) {
        val connected = _state.value as? PairingState.Success
        if (connected?.deviceId != deviceId || activeSessionJob == null) return
        updateClipboardMonitor(deviceId)
    }

    fun unpairDevice(deviceId: String): Boolean {
        val removed = trustStore.remove(deviceId)
        devicePermissionStore.remove(deviceId)
        notificationBlocklistStore.removeDevice(deviceId)
        safeNetworkStore.removeDevice(deviceId)
        lastAutoConnectAttemptAt.keys
            .filter { key -> key == deviceId || key.startsWith("$deviceId:") }
            .forEach(lastAutoConnectAttemptAt::remove)
        val state = _state.value
        if (state is PairingState.Success && state.deviceId == deviceId) {
            closeActiveSession()
        } else if (removed) {
            // A reconnect may currently be blocked in Socket.connect/read.
            closeConnectingSocket()
        }
        if (removed) _state.value = PairingState.Idle
        DebugEventLog.record(
            "pairing",
            if (removed) "Unpaired trusted desktop $deviceId" else "Trusted desktop $deviceId was not found",
        )
        return removed
    }

    fun trustCurrentWifiForTrustedDevices(): Boolean {
        val trusted = trustStore.listRecords()
        if (trusted.isEmpty()) return safeNetworkStore.currentWifiNetwork() != null
        var trustedAny = false
        trusted.forEach { device ->
            trustedAny = safeNetworkStore.trustCurrentNetwork(device.deviceId, device.deviceName) || trustedAny
        }
        return trustedAny
    }

    fun startPairing(device: DiscoveredDevice) {
        if (pendingSession != null) {
            DebugEventLog.record("connection", "Pairing confirmation is already in progress")
            return
        }
        if (activeSessionJob?.isActive == true) {
            DebugEventLog.record("connection", "A secure desktop session is already active")
            return
        }
        if (!connectionAttemptInFlight.compareAndSet(false, true)) {
            DebugEventLog.record("connection", "Ignored duplicate connect request while another attempt is active")
            return
        }
        DebugEventLog.record("connection", "Connecting to ${device.deviceName} at ${device.endpoint}")
        scope.launch {
            try {
                _state.value = PairingState.Connecting(device.deviceName)
                runCatching {
                    val trustedDevice = trustedDeviceFor(device)
                    if (trustedDevice != null) {
                        if (!safeNetworkStore.isCurrentNetworkTrusted(trustedDevice.deviceId)) {
                            _state.value = PairingState.Error(
                                "Safe Wi-Fi is enabled and this Wi-Fi is not allowed for ${trustedDevice.deviceName}. Open Safe Wi-Fi, grant Location, and enable this network.",
                            )
                            return@runCatching
                        }
                        if (safeAttemptTrustedReconnect(device, trustedDevice)) {
                            return@runCatching
                        }
                        if (trustStore.get(trustedDevice.deviceId) == null) {
                            _state.value = PairingState.Idle
                            return@runCatching
                        }
                        _state.value = PairingState.Error(
                            "Trusted reconnect to ${trustedDevice.deviceName} failed. Linkable will keep retrying automatically; forget the stale pairing if the desktop was reset.",
                        )
                        return@runCatching
                    } else if (!safeNetworkStore.allowAllWifi() && safeNetworkStore.currentWifiNetwork() == null) {
                        _state.value = PairingState.Error(
                            "Safe Wi-Fi is enabled, but the current Wi-Fi could not be read. Grant Location while using the app and keep Wi-Fi connected.",
                        )
                        return@runCatching
                    }
                    startFullPairing(device)
                }.onFailure { error ->
                    closePendingSession()
                    DebugEventLog.record("connection", "Connection failed: ${error.message}")
                    _state.value = PairingState.Error(error.message ?: "Failed to start pairing.")
                }
            } finally {
                connectionAttemptInFlight.set(false)
            }
        }
    }

    fun autoConnectTrusted(devices: List<DiscoveredDevice>) {
        if (!canStartAutomaticReconnect()) return
        val trustedCandidates = devices.mapNotNull { device ->
            trustedDeviceFor(device)?.let { trusted -> device to trusted }
        }.distinctBy { (_, trusted) -> trusted.deviceId }
        if (trustedCandidates.isEmpty()) return
        if (trustedCandidates.size > 1) {
            DebugEventLog.record(
                "connection",
                "Multiple trusted desktops are visible; automatic reconnect paused until user chooses one.",
            )
            return
        }
        val (device, trusted) = trustedCandidates.single()
        val now = System.currentTimeMillis()
        val lastAttempt = lastAutoConnectAttemptAt[trusted.deviceId] ?: 0L
        if (now - lastAttempt < AUTO_RECONNECT_COOLDOWN_MS) return
        if (!connectionAttemptInFlight.compareAndSet(false, true)) return
        lastAutoConnectAttemptAt[trusted.deviceId] = now
        DebugEventLog.record("connection", "Auto-reconnecting to trusted desktop ${trusted.deviceName}")
        scope.launch {
            try {
                reconnectTrustedWithBackoff(
                    device = device,
                    trustedDevice = trusted,
                    initialDetail = "Trusted desktop is visible on LAN.",
                )
            } finally {
                connectionAttemptInFlight.set(false)
            }
        }
    }

    suspend fun autoConnectTrustedFallback() {
        if (!canStartAutomaticReconnect()) return
        val trusted = trustStore.listRecords().singleOrNull() ?: return
        if (!safeNetworkStore.isCurrentNetworkTrusted(trusted.deviceId)) return
        val now = System.currentTimeMillis()
        val key = "${trusted.deviceId}:fallback"
        val lastAttempt = lastAutoConnectAttemptAt[key] ?: 0L
        if (now - lastAttempt < FALLBACK_RECONNECT_COOLDOWN_MS) return
        val candidates = fallbackTrustedReconnectCandidates(trusted)
        if (candidates.isEmpty()) return
        if (!connectionAttemptInFlight.compareAndSet(false, true)) return

        try {
            lastAutoConnectAttemptAt[key] = now
            DebugEventLog.record(
                "connection",
                "Trying trusted LAN fallback for ${trusted.deviceName} across ${candidates.size} nearby endpoints",
            )
            for (candidate in candidates) {
                if (activeSessionJob != null || pendingSession != null) return
                if (safeAttemptTrustedReconnect(candidate, trusted, connectTimeoutMs = FALLBACK_CONNECT_TIMEOUT_MS)) {
                    DebugEventLog.record("connection", "Trusted LAN fallback connected to ${trusted.deviceName} at ${candidate.endpoint}")
                    return
                }
            }
        } finally {
            connectionAttemptInFlight.set(false)
        }
    }

    fun confirmDisplayedCodeEntry() {
        val session = pendingSession ?: return
        if (!pairingConfirmationInFlight.compareAndSet(false, true)) {
            return
        }
        scope.launch {
            try {
                runCatching {
                    val transcriptHash = CryptoUtils.computeTranscriptHash(
                    pairingNonce = session.request.pairingNonce.toByteArray(),
                    challengeNonce = session.challenge.challengeNonce.toByteArray(),
                    initiatorDeviceId = identity.deviceId,
                    acceptorDeviceId = session.challenge.acceptor.deviceId.fingerprint,
                    verificationCode = session.code,
                )

                val confirm = PairingConfirm.newBuilder()
                    .setConfirmer(buildPeerDescriptor())
                    .setTranscriptHash(com.google.protobuf.ByteString.copyFrom(transcriptHash))
                    .setTranscriptSignature(com.google.protobuf.ByteString.copyFrom(identity.sign(transcriptHash)))
                    .build()
                session.io.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_PAIRING_CONFIRM,
                        message = confirm,
                        sequenceNumber = nextSequence(),
                    ),
                )

                val desktopConfirmEnvelope = session.io.readEnvelope()
                if (desktopConfirmEnvelope.packetType == PacketType.PACKET_TYPE_PAIRING_REJECT) {
                    val reject = PairingReject.parseFrom(desktopConfirmEnvelope.payload)
                    throw IllegalStateException("Pairing rejected: ${reject.detail}")
                }
                require(desktopConfirmEnvelope.packetType == PacketType.PACKET_TYPE_PAIRING_CONFIRM) {
                    "Expected desktop PairingConfirm"
                }
                val desktopConfirm = PairingConfirm.parseFrom(desktopConfirmEnvelope.payload)
                val acceptorPublicKey = session.challenge.acceptor.identityPublicKey.toByteArray()
                require(desktopConfirm.transcriptHash.toByteArray().contentEquals(transcriptHash)) {
                    "Transcript mismatch from desktop"
                }
                require(
                    DeviceIdentity.verify(
                        publicKeyBytes = acceptorPublicKey,
                        payload = transcriptHash,
                        signatureBytes = desktopConfirm.transcriptSignature.toByteArray(),
                    ),
                ) {
                    "Desktop signature invalid"
                }

                val completeEnvelope = session.io.readEnvelope()
                require(completeEnvelope.packetType == PacketType.PACKET_TYPE_PAIRING_COMPLETE) {
                    "Expected PairingComplete"
                }
                PairingComplete.parseFrom(completeEnvelope.payload)

                val trustedDevice = TrustStore.trustedDeviceFromPublicKey(
                    deviceId = session.challenge.acceptor.deviceId.fingerprint,
                    deviceName = session.challenge.acceptor.deviceName,
                    publicKeyBytes = acceptorPublicKey,
                    pairedAtEpochMs = System.currentTimeMillis(),
                )
                trustStore.upsert(trustedDevice)
                safeNetworkStore.trustCurrentNetwork(
                    deviceId = trustedDevice.deviceId,
                    deviceName = trustedDevice.deviceName,
                    requireCurrent = !safeNetworkStore.allowAllWifi(),
                )
                session.socket.close()
                pendingSession = null
                _state.value = PairingState.Success(
                    deviceName = session.challenge.acceptor.deviceName,
                    deviceId = session.challenge.acceptor.deviceId.fingerprint,
                    reusedTrust = false,
                )
                DebugEventLog.record("pairing", "Paired with ${session.challenge.acceptor.deviceName}")
                DebugEventLog.record("session", "Opening encrypted session after pairing")
                if (!safeAttemptTrustedReconnect(session.device, trustedDevice)) {
                    _state.value = PairingState.Error(
                        "Pairing succeeded, but the live session did not open. Linkable will reconnect automatically.",
                    )
                }
                }.onFailure { error ->
                    closePendingSession()
                    DebugEventLog.record("pairing", "Pairing failed: ${error.message}")
                    _state.value = PairingState.Error(error.message ?: "Failed to complete pairing.")
                }
            } finally {
                pairingConfirmationInFlight.set(false)
            }
        }
    }

    fun reset() {
        closePendingSession()
        closeConnectingSocket()
        closeActiveSession()
        _state.value = PairingState.Idle
    }

    fun sendFile(uri: Uri) {
        val accepted = outboundFiles.trySend(uri).isSuccess
        if (accepted) {
            SessionEventSignal.notifyPendingWork()
            DebugEventLog.record(
                "transfer",
                if (activeSessionJob == null) {
                    "Queued selected file; connect to desktop to send"
                } else {
                    "Queued selected file for desktop"
                },
            )
        } else {
            DebugEventLog.record("transfer", "Failed to queue selected file")
        }
    }

    fun sendDesktopInput(request: DesktopInputRequest) {
        val accepted = outboundDesktopInput.trySend(request).isSuccess
        if (accepted) {
            SessionEventSignal.notifyPendingWork()
        }
        DebugEventLog.record(
            "input",
            if (accepted) {
                "Queued desktop input action ${request.actionType}"
            } else {
                "Failed to queue desktop input action ${request.actionType}"
            },
        )
    }

    fun approvePendingCameraRequest() {
        val result = CameraStreamController.approvePending(appContext)
        if (result == null) {
            DebugEventLog.record("camera", "No pending camera request to approve.")
            return
        }
        if (outboundCameraStartResults.trySend(result).isSuccess) {
            SessionEventSignal.notifyPendingWork()
        }
        if (!result.success) {
            CameraStreamingService.stop(appContext)
        }
    }

    fun rejectPendingCameraRequest() {
        val result = CameraStreamController.rejectPending()
        if (result == null) {
            DebugEventLog.record("camera", "No pending camera request to reject.")
            return
        }
        if (outboundCameraStartResults.trySend(result).isSuccess) {
            SessionEventSignal.notifyPendingWork()
        }
        CameraStreamingService.stop(appContext)
    }

    fun stopCameraFromPhone() {
        CameraStreamController.stopAny("phone user stopped camera")
        CameraStreamingService.stop(appContext)
    }

    fun shutdown() {
        closePendingSession()
        closeConnectingSocket()
        closeActiveSession()
    }

    private fun canStartAutomaticReconnect(): Boolean {
        if (connectionAttemptInFlight.get()) return false
        if (activeSessionJob != null || pendingSession != null) return false
        return when (_state.value) {
            is PairingState.Connecting,
            is PairingState.AwaitingCodeEntry,
            is PairingState.PairingInProgress,
            is PairingState.Reconnecting -> false
            is PairingState.Success -> activeSessionJob == null
            is PairingState.Error,
            PairingState.Idle -> true
        }
    }

    private fun buildPeerDescriptor(): PeerDescriptor {
        val local = identity.localDescriptor()
        return PeerDescriptor.newBuilder()
            .setDeviceId(DeviceId.newBuilder().setFingerprint(local.deviceId).build())
            .setDeviceName(local.deviceName)
            .setPlatform("android")
            .setProtocolVersion(
                ProtocolVersion.newBuilder().setMajor(1).setMinor(0).setPatch(0).build(),
            )
            .setIdentityPublicKey(com.google.protobuf.ByteString.copyFrom(local.publicKeyBytes))
            .build()
    }

    private fun nextSequence(): Long = sequenceCounter.getAndIncrement()

    private fun randomNonce(): ByteArray = ByteArray(32).also { java.security.SecureRandom().nextBytes(it) }

    private fun openCameraApprovalUi() {
        runCatching {
            appContext.startActivity(
                Intent(appContext, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                    putExtra("linkable_camera_request", true)
                },
            )
        }.onFailure { error ->
            DebugEventLog.record("camera", "Open camera approval UI from background failed: ${error.message}")
        }
    }

    private fun trustedDeviceFor(device: DiscoveredDevice): TrustedDevice? {
        trustStore.get(device.deviceId)?.let { return it }
        if (device.source.name != "DIRECT_CONNECT") return null
        val records = trustStore.listRecords()
        return records.singleOrNull()
    }

    private fun startFullPairing(device: DiscoveredDevice) {
        val socket = Socket()
        connectingSocket = socket
        try {
            socket.connect(InetSocketAddress(device.host, device.port), 5_000)
            socket.soTimeout = 30_000
            val io = ConnectionIO(socket.getInputStream(), socket.getOutputStream())

            val request = PairingRequest.newBuilder()
                .setInitiator(buildPeerDescriptor())
                .setPairingNonce(com.google.protobuf.ByteString.copyFrom(randomNonce()))
                .setDirectConnect(device.source.name == "DIRECT_CONNECT")
                .build()
            io.writeEnvelope(
                ConnectionIO.buildEnvelope(
                    packetType = PacketType.PACKET_TYPE_PAIRING_REQUEST,
                    message = request,
                    sequenceNumber = nextSequence(),
                ),
            )

            val responseEnvelope = io.readEnvelope()
            when (responseEnvelope.packetType) {
                PacketType.PACKET_TYPE_PAIRING_CHALLENGE -> {
                    val challenge = PairingChallenge.parseFrom(responseEnvelope.payload)
                    val code = CryptoUtils.derivePairingCode(
                        pairingNonce = request.pairingNonce.toByteArray(),
                        challengeNonce = challenge.challengeNonce.toByteArray(),
                        initiatorPublicKey = identity.publicKeyBytes,
                        acceptorPublicKey = challenge.acceptor.identityPublicKey.toByteArray(),
                        codeLength = challenge.verificationCodeLength,
                    )
                    val session = PendingPairingSession(device, socket, io, request, challenge, code)
                    pendingSession = session
                    _state.value = PairingState.AwaitingCodeEntry(device.deviceName, code)
                    scope.launch {
                        delay(500)
                        if (pendingSession === session) {
                            confirmDisplayedCodeEntry()
                        }
                    }
                }

                PacketType.PACKET_TYPE_PAIRING_REJECT -> {
                    val reject = PairingReject.parseFrom(responseEnvelope.payload)
                    throw IllegalStateException("Pairing rejected: ${reject.detail}")
                }

                else -> {
                    throw IllegalStateException("Unexpected response during pairing.")
                }
            }
        } catch (error: Throwable) {
            runCatching { socket.close() }
            throw error
        } finally {
            if (connectingSocket === socket) {
                connectingSocket = null
            }
        }
    }

    private suspend fun attemptTrustedReconnect(
        device: DiscoveredDevice,
        trustedDevice: TrustedDevice,
        connectTimeoutMs: Int = 5_000,
    ): Boolean {
        if (!safeNetworkStore.isCurrentNetworkTrusted(trustedDevice.deviceId)) {
            DebugEventLog.record(
                "network",
                "Blocked ${trustedDevice.deviceName}; Safe Wi-Fi is enabled and current Wi-Fi is not allowed.",
            )
            return false
        }
        val socket = Socket()
        connectingSocket = socket
        var keepSocketOpen = false
        try {
            socket.connect(InetSocketAddress(device.host, device.port), connectTimeoutMs)
            socket.soTimeout = 20_000
            val io = ConnectionIO(socket.getInputStream(), socket.getOutputStream())
            val descriptor = buildPeerDescriptor()
            val issuedAtMs = System.currentTimeMillis()
            val ephemeral = SessionCipher.generateEphemeralKeyPair()
            val signaturePayload = CryptoUtils.buildSessionSignaturePayload(
                label = "linkable-session-init-v1",
                descriptor = descriptor,
                ephemeralPublicKey = ephemeral.publicKeyBytes,
                issuedAtMs = issuedAtMs,
            )
            val sessionInit = SessionInit.newBuilder()
                .setInitiator(descriptor)
                .setEphemeralPublicKey(com.google.protobuf.ByteString.copyFrom(ephemeral.publicKeyBytes))
                .setIdentitySignature(com.google.protobuf.ByteString.copyFrom(identity.sign(signaturePayload)))
                .setIssuedAt(Timestamp.newBuilder().setUnixEpochMs(issuedAtMs).build())
                .build()
            io.writeEnvelope(
                ConnectionIO.buildEnvelope(
                    packetType = PacketType.PACKET_TYPE_SESSION_INIT,
                    message = sessionInit,
                    sequenceNumber = nextSequence(),
                ),
            )

            val responseEnvelope = io.readEnvelope()
            when (responseEnvelope.packetType) {
                PacketType.PACKET_TYPE_SESSION_ACK -> {
                    val ack = SessionAck.parseFrom(responseEnvelope.payload)
                    require(ack.acceptor.deviceId.fingerprint == trustedDevice.deviceId) {
                        "Trusted reconnect returned an unexpected device ID."
                    }
                    require(
                        ack.acceptor.identityPublicKey.toByteArray().contentEquals(trustedDevice.publicKeyBytes),
                    ) {
                        "Trusted reconnect returned an unexpected identity key."
                    }
                    require(
                        CryptoUtils.isTimestampFresh(
                            issuedAtMs = ack.issuedAt.unixEpochMs,
                            maxSkewMs = 120_000,
                        ),
                    ) {
                        "Trusted reconnect acknowledgement is stale."
                    }
                    val ackPayload = CryptoUtils.buildSessionSignaturePayload(
                        label = "linkable-session-ack-v1",
                        descriptor = ack.acceptor,
                        ephemeralPublicKey = ack.ephemeralPublicKey.toByteArray(),
                        issuedAtMs = ack.issuedAt.unixEpochMs,
                    )
                    require(
                        DeviceIdentity.verify(
                            publicKeyBytes = trustedDevice.publicKeyBytes,
                            payload = ackPayload,
                            signatureBytes = ack.identitySignature.toByteArray(),
                        ),
                    ) {
                        "Trusted reconnect signature verification failed."
                    }
                    if (trustStore.get(trustedDevice.deviceId) == null) {
                        return false
                    }
                    val transportSummary = startActiveEncryptedSession(
                        device = device,
                        trustedDevice = trustedDevice,
                        socket = socket,
                        ephemeral = ephemeral,
                        ack = ack,
                    )
                    keepSocketOpen = true
                    _state.value = PairingState.Success(
                        deviceName = trustedDevice.deviceName,
                        deviceId = trustedDevice.deviceId,
                        reusedTrust = true,
                        transportSummary = transportSummary,
                    )
                    DebugEventLog.record("session", "Trusted encrypted session active with ${trustedDevice.deviceName}")
                    return true
                }

                PacketType.PACKET_TYPE_SESSION_CLOSE -> {
                    val close = SessionClose.parseFrom(responseEnvelope.payload)
                    if (close.reason == SessionCloseReason.SESSION_CLOSE_REASON_REVOKED) {
                        trustStore.remove(trustedDevice.deviceId)
                        devicePermissionStore.remove(trustedDevice.deviceId)
                        notificationBlocklistStore.removeDevice(trustedDevice.deviceId)
                        safeNetworkStore.removeDevice(trustedDevice.deviceId)
                        DebugEventLog.record("connection", "Desktop revoked trust for ${trustedDevice.deviceName}; cleared stale local trust.")
                    }
                    return false
                }

                else -> return false
            }
        } finally {
            if (connectingSocket === socket) {
                connectingSocket = null
            }
            if (!keepSocketOpen) {
                runCatching { socket.close() }
            }
        }
    }

    private suspend fun safeAttemptTrustedReconnect(
        device: DiscoveredDevice,
        trustedDevice: TrustedDevice,
        connectTimeoutMs: Int = 5_000,
    ): Boolean {
        return runCatching {
            attemptTrustedReconnect(device, trustedDevice, connectTimeoutMs)
        }.onFailure { error ->
            DebugEventLog.record(
                "connection",
                "Trusted reconnect to ${trustedDevice.deviceName} failed: ${error.message ?: error.javaClass.simpleName}",
            )
        }.getOrDefault(false)
    }

    private fun fallbackTrustedReconnectCandidates(trustedDevice: TrustedDevice): List<DiscoveredDevice> {
        return nearbyWifiHosts().map { host ->
            DiscoveredDevice(
                serviceName = "fallback://$host:37891",
                deviceName = trustedDevice.deviceName,
                host = host,
                port = 37891,
                protocolVersion = "trusted-fallback",
                deviceId = trustedDevice.deviceId,
                source = DiscoverySource.DIRECT_CONNECT,
            )
        }
    }

    @Suppress("DEPRECATION")
    private fun nearbyWifiHosts(): List<String> {
        val dhcpInfo = wifiManager?.dhcpInfo ?: return emptyList()
        val own = ipv4LittleEndianToOctets(dhcpInfo.ipAddress) ?: return emptyList()
        val gateway = ipv4LittleEndianToOctets(dhcpInfo.gateway)
        val prefix = own.take(3).joinToString(".")
        val ownLast = own[3]
        val candidates = mutableListOf<Int>()
        gateway?.getOrNull(3)?.let { candidates.add(it) }
        for (offset in 1..FALLBACK_NEARBY_HOST_RADIUS) {
            candidates.add(ownLast - offset)
            candidates.add(ownLast + offset)
        }
        candidates.add(1)
        candidates.add(254)
        return candidates
            .filter { it in 1..254 && it != ownLast }
            .distinct()
            .map { "$prefix.$it" }
    }

    private fun ipv4LittleEndianToOctets(value: Int): List<Int>? {
        if (value == 0) return null
        return listOf(
            value and 0xff,
            value shr 8 and 0xff,
            value shr 16 and 0xff,
            value shr 24 and 0xff,
        )
    }

    private suspend fun startActiveEncryptedSession(
        device: DiscoveredDevice,
        trustedDevice: TrustedDevice,
        socket: Socket,
        ephemeral: EphemeralKeyPair,
        ack: SessionAck,
    ): String {
        val keys = SessionCipher.deriveDirectionalKeys(
            privateKey = ephemeral.privateKey,
            peerPublicKeyBytes = ack.ephemeralPublicKey.toByteArray(),
            initiatorPublicKeyBytes = ephemeral.publicKeyBytes,
            acceptorPublicKeyBytes = ack.ephemeralPublicKey.toByteArray(),
        )
        val encrypted = EncryptedConnection(
            input = socket.getInputStream(),
            output = socket.getOutputStream(),
            sendKey = keys.clientToServer,
            receiveKey = keys.serverToClient,
        )
        val pingToken = UUID.randomUUID().toString()
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_PING,
                message = Ping.newBuilder()
                    .setToken(pingToken)
                    .setSentAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
                    .build(),
                sequenceNumber = nextSequence(),
            ),
        )
        val pongEnvelope = encrypted.readEnvelope()
        require(pongEnvelope.packetType == PacketType.PACKET_TYPE_PONG) { "Expected encrypted Pong" }
        val pong = Pong.parseFrom(pongEnvelope.payload)
        require(pong.token == pingToken) { "Encrypted Pong token mismatch" }

        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_DEVICE_INFO_REQUEST,
                message = DeviceInfoRequest.newBuilder().build(),
                sequenceNumber = nextSequence(),
            ),
        )
        val deviceInfoEnvelope = encrypted.readEnvelope()
        require(deviceInfoEnvelope.packetType == PacketType.PACKET_TYPE_DEVICE_INFO_RESPONSE) {
            "Expected encrypted DeviceInfoResponse"
        }
        val deviceInfo = DeviceInfoResponse.parseFrom(deviceInfoEnvelope.payload)

        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_CAPABILITIES_REQUEST,
                message = CapabilitiesRequest.newBuilder().build(),
                sequenceNumber = nextSequence(),
            ),
        )
        val capabilitiesEnvelope = encrypted.readEnvelope()
        require(capabilitiesEnvelope.packetType == PacketType.PACKET_TYPE_CAPABILITIES_RESPONSE) {
            "Expected encrypted CapabilitiesResponse"
        }
        val capabilities = CapabilitiesResponse.parseFrom(capabilitiesEnvelope.payload)

        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_HEARTBEAT,
                message = Heartbeat.newBuilder()
                    .setSentAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
                    .setSenderRole(Role.ROLE_INITIATOR)
                    .build(),
                sequenceNumber = nextSequence(),
            ),
        )
        socket.soTimeout = 0
        closeActiveSession()
        activeSocket = socket
        callStateMonitor.start()
        updateClipboardMonitor(trustedDevice.deviceId)
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_PHONE_CAPABILITY_SNAPSHOT,
                message = telephonyDiagnosticsProvider.capabilitySnapshot(),
                sequenceNumber = nextSequence(),
            ),
        )
        sendSharedAppsSnapshot(encrypted, trustedDevice)
        activeSessionJob = scope.launch {
            runHeartbeatLoop(
                device = device,
                trustedDevice = trustedDevice,
                encrypted = encrypted,
                socket = socket,
            )
        }
        return "Encrypted ping ok; live heartbeat active; ${deviceInfo.peer.deviceName}; ${capabilities.capabilitiesCount} capabilities"
    }

    private suspend fun runHeartbeatLoop(
        device: DiscoveredDevice,
        trustedDevice: TrustedDevice,
        encrypted: EncryptedConnection,
        socket: Socket,
    ) {
        try {
            coroutineScope {
                val reader = launch(Dispatchers.IO) {
                    try {
                        while (currentCoroutineContext().isActive) {
                            handleDesktopEnvelope(
                                encrypted = encrypted,
                                trustedDevice = trustedDevice,
                                desktopHost = device.host,
                                envelope = encrypted.readEnvelope(),
                            )
                        }
                    } catch (error: Throwable) {
                        runCatching { socket.close() }
                        throw error
                    }
                }
                val writer = launch(Dispatchers.IO) {
                    var lastHeartbeatAt = System.currentTimeMillis()
                    var lastSharedAppsSnapshotAt = System.currentTimeMillis()
                    try {
                        var pendingWorkRemains = drainPendingLocalEvents(encrypted, trustedDevice)
                        while (currentCoroutineContext().isActive) {
                            if (!pendingWorkRemains) {
                                val waitMs = (ACTIVE_HEARTBEAT_INTERVAL_MS -
                                    (System.currentTimeMillis() - lastHeartbeatAt)).coerceAtLeast(1L)
                                withTimeoutOrNull(waitMs) {
                                    SessionEventSignal.events.receive()
                                }
                            }
                            pendingWorkRemains = drainPendingLocalEvents(encrypted, trustedDevice)

                            val now = System.currentTimeMillis()
                            if (now - lastHeartbeatAt >= ACTIVE_HEARTBEAT_INTERVAL_MS) {
                                encrypted.writeEnvelope(
                                    ConnectionIO.buildEnvelope(
                                        packetType = PacketType.PACKET_TYPE_HEARTBEAT,
                                        message = Heartbeat.newBuilder()
                                            .setSentAt(Timestamp.newBuilder().setUnixEpochMs(now).build())
                                            .setSenderRole(Role.ROLE_INITIATOR)
                                            .build(),
                                        sequenceNumber = nextSequence(),
                                    ),
                                )
                                if (now - lastSharedAppsSnapshotAt >= SHARED_APPS_SNAPSHOT_INTERVAL_MS) {
                                    sendSharedAppsSnapshot(encrypted, trustedDevice)
                                    lastSharedAppsSnapshotAt = now
                                }
                                lastHeartbeatAt = now
                            }
                        }
                    } catch (error: Throwable) {
                        runCatching { socket.close() }
                        throw error
                    }
                }
                reader.join()
                writer.cancelAndJoin()
            }
        } catch (error: CancellationException) {
            runCatching { socket.close() }
            callStateMonitor.stop()
            throw error
        } catch (error: Throwable) {
            runCatching { socket.close() }
            activeSessionJob = null
            callStateMonitor.stop()
            PhoneClipboardMonitor.stop()
            if (currentCoroutineContext().isActive && trustStore.get(trustedDevice.deviceId) != null) {
                retryTrustedReconnect(device, trustedDevice, error)
            }
        }
    }

    private fun drainPendingLocalEvents(
        encrypted: EncryptedConnection,
        trustedDevice: TrustedDevice,
    ): Boolean {
        var processed = 0
        while (processed < MAX_LOCAL_EVENTS_PER_TICK) {
            var didWork = false

            CallStateBridge.events.tryReceive().getOrNull()?.let { callEvent ->
                didWork = true
                if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).calls) {
                    forwardCallStateEvent(encrypted, trustedDevice, callEvent)
                }
            }

            CallStateBridge.metadataEvents.tryReceive().getOrNull()?.let { callMetadataEvent ->
                didWork = true
                if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).calls) {
                    forwardCallMetadataEvent(encrypted, trustedDevice, callMetadataEvent)
                }
            }

            NotificationBridge.events.tryReceive().getOrNull()?.let { notificationEvent ->
                didWork = true
                val permissions = devicePermissionStore.permissionsFor(trustedDevice.deviceId)
                val gateReason = notificationGateReason(permissions, notificationEvent)
                if (gateReason != null) {
                    logPermissionDrop(trustedDevice.deviceId, "notification", gateReason)
                } else if (shouldForwardNotificationToDevice(trustedDevice.deviceId, notificationEvent)) {
                    forwardNotificationEvent(encrypted, trustedDevice, notificationEvent)
                } else {
                    logPermissionDrop(
                        trustedDevice.deviceId,
                        "notification-filter",
                        "Notification was blocked by the per-app notification filter.",
                    )
                }
            }

            outboundFiles.tryReceive().getOrNull()?.let { uri ->
                didWork = true
                if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).files) {
                    runCatching {
                        phoneFileSender.send(
                            encrypted = encrypted,
                            uri = uri,
                            nextSequence = ::nextSequence,
                        )
                    }.onFailure { error ->
                        DebugEventLog.record("transfer", "Phone file send failed: ${error.message}")
                    }
                } else {
                    DebugEventLog.record("transfer", "Selected file was not sent; file transfer is disabled for this PC.")
                }
            }

            outboundDesktopInput.tryReceive().getOrNull()?.let { request ->
                didWork = true
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_DESKTOP_INPUT_REQUEST,
                        message = request,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("input", "Sent desktop input action ${request.actionType}")
            }

            PhoneClipboardMonitor.events.tryReceive().getOrNull()?.let { update ->
                didWork = true
                if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).forwardClipboardToPc) {
                    encrypted.writeEnvelope(
                        ConnectionIO.buildEnvelope(
                            packetType = PacketType.PACKET_TYPE_CLIPBOARD_UPDATE,
                            message = update,
                            sequenceNumber = nextSequence(),
                        ),
                    )
                    DebugEventLog.record("clipboard", "Forwarded clipboard update to ${trustedDevice.deviceName}")
                } else {
                    logPermissionDrop(
                        trustedDevice.deviceId,
                        "clipboard",
                        "Mobile clipboard forwarding is disabled for this PC.",
                    )
                }
            }

            outboundCameraStartResults.tryReceive().getOrNull()?.let { result ->
                didWork = true
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_CAMERA_STREAM_START_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("camera", result.detail)
            }

            CameraStreamController.statusEvents.tryReceive().getOrNull()?.let { event ->
                didWork = true
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_CAMERA_STREAM_STATUS_EVENT,
                        message = event,
                        sequenceNumber = nextSequence(),
                    ),
                )
            }

            var framesSent = 0
            while (framesSent < MAX_CAMERA_FRAMES_PER_TICK) {
                val frame = CameraStreamController.frameEvents.tryReceive().getOrNull() ?: break
                didWork = true
                framesSent += 1
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_CAMERA_FRAME,
                        message = frame,
                        sequenceNumber = nextSequence(),
                    ),
                )
            }

            if (!didWork) {
                return false
            }
            processed += 1
        }
        return true
    }

    private fun handleDesktopEnvelope(
        encrypted: EncryptedConnection,
        trustedDevice: TrustedDevice,
        desktopHost: String,
        envelope: com.linkable.protocol.v1.Envelope,
    ) {
        when (envelope.packetType) {
            PacketType.PACKET_TYPE_NOTIFICATION_REPLY_REQUEST -> {
                val request = com.linkable.protocol.v1.NotificationReplyRequest.parseFrom(envelope.payload)
                val result = NotificationActionStore.executeReply(appContext, request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_NOTIFICATION_REPLY_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Desktop reply sent for notification ${request.notificationId}"
                    } else {
                        "Desktop reply failed: ${result.detail}"
                    },
                )
                DebugEventLog.record("reply", if (result.success) "Reply sent" else "Reply failed: ${result.detail}")
            }

            PacketType.PACKET_TYPE_NOTIFICATION_ACTION_REQUEST -> {
                val request = com.linkable.protocol.v1.NotificationActionRequest.parseFrom(envelope.payload)
                val result = NotificationActionStore.executeAction(appContext, request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_NOTIFICATION_ACTION_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Desktop notification action sent for ${request.notificationId}"
                    } else {
                        "Desktop notification action failed: ${result.detail}"
                    },
                )
                DebugEventLog.record(
                    "notification",
                    if (result.success) {
                        "Notification action sent"
                    } else {
                        "Notification action failed: ${result.detail}"
                    },
                )
            }

            PacketType.PACKET_TYPE_FILE_OFFER -> {
                val offer = com.linkable.protocol.v1.FileOffer.parseFrom(envelope.payload)
                if (!devicePermissionStore.permissionsFor(trustedDevice.deviceId).files) {
                    encrypted.writeEnvelope(
                        ConnectionIO.buildEnvelope(
                            packetType = PacketType.PACKET_TYPE_FILE_TRANSFER_RESULT,
                            message = blockedFileTransferResult(offer.transferId, "File sharing is disabled for this PC."),
                            sequenceNumber = nextSequence(),
                        ),
                    )
                    DebugEventLog.record("transfer", "Blocked incoming PC file ${offer.fileName}; file transfer is disabled for this PC.")
                    return
                }
                val result = fileTransferReceiver.handleOffer(offer)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_FILE_TRANSFER_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = "Receiving file: ${offer.fileName} (${offer.sizeBytes} bytes)",
                )
                DebugEventLog.record("transfer", "Incoming PC file accepted: ${offer.fileName}")
            }

            PacketType.PACKET_TYPE_FILE_CHUNK -> {
                val chunk = com.linkable.protocol.v1.FileChunk.parseFrom(envelope.payload)
                fileTransferReceiver.handleChunk(chunk)?.let { result ->
                    encrypted.writeEnvelope(
                        ConnectionIO.buildEnvelope(
                            packetType = PacketType.PACKET_TYPE_FILE_TRANSFER_RESULT,
                            message = result,
                            sequenceNumber = nextSequence(),
                        ),
                    )
                }
            }

            PacketType.PACKET_TYPE_FILE_COMPLETE -> {
                val complete = com.linkable.protocol.v1.FileComplete.parseFrom(envelope.payload)
                val result = fileTransferReceiver.handleComplete(complete)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_FILE_TRANSFER_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "File received: ${result.savedPath}"
                    } else {
                        "File transfer failed: ${result.detail}"
                    },
                )
                DebugEventLog.record(
                    "transfer",
                    if (result.success) {
                        "Received PC file: ${result.savedPath}"
                    } else {
                        "PC file receive failed: ${result.detail}"
                    },
                )
            }

            PacketType.PACKET_TYPE_FILE_TRANSFER_RESULT -> {
                val result = com.linkable.protocol.v1.FileTransferResult.parseFrom(envelope.payload)
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Desktop saved file: ${result.savedPath}"
                    } else {
                        "Desktop file receive failed: ${result.detail}"
                    },
                )
                DebugEventLog.record(
                    "transfer",
                    if (result.success) {
                        "Desktop saved phone file: ${result.savedPath}"
                    } else {
                        "Desktop rejected file: ${result.detail}"
                    },
                )
            }

            PacketType.PACKET_TYPE_DESKTOP_INPUT_RESULT -> {
                val result = DesktopInputResult.parseFrom(envelope.payload)
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Desktop input ok: ${result.detail}"
                    } else {
                        "Desktop input failed: ${result.detail}"
                    },
                )
                DebugEventLog.record("input", if (result.success) result.detail else "Failed: ${result.detail}")
            }

            PacketType.PACKET_TYPE_RING_PHONE_REQUEST -> {
                val request = com.linkable.protocol.v1.RingPhoneRequest.parseFrom(envelope.payload)
                val result = phoneRinger.handle(request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_RING_PHONE_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Phone utility: ${result.detail}"
                    } else {
                        "Phone utility failed: ${result.detail}"
                    },
                )
                DebugEventLog.record("utility", result.detail)
            }

            PacketType.PACKET_TYPE_CALL_CONTROL_REQUEST -> {
                val request = com.linkable.protocol.v1.CallControlRequest.parseFrom(envelope.payload)
                if (!devicePermissionStore.permissionsFor(trustedDevice.deviceId).calls) {
                    encrypted.writeEnvelope(
                        ConnectionIO.buildEnvelope(
                            packetType = PacketType.PACKET_TYPE_CALL_CONTROL_RESULT,
                            message = callControlBlockedResult(request, "Call sharing is disabled for this PC."),
                            sequenceNumber = nextSequence(),
                        ),
                    )
                    return
                }
                val result = callControlHandler.handle(request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_CALL_CONTROL_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Call control: ${result.detail}"
                    } else {
                        "Call control failed: ${result.detail}"
                    },
                )
                DebugEventLog.record("call", result.detail)
            }

            PacketType.PACKET_TYPE_DIAL_REQUEST -> {
                val request = com.linkable.protocol.v1.DialRequest.parseFrom(envelope.payload)
                if (!devicePermissionStore.permissionsFor(trustedDevice.deviceId).calls) {
                    encrypted.writeEnvelope(
                        ConnectionIO.buildEnvelope(
                            packetType = PacketType.PACKET_TYPE_DIAL_RESULT,
                            message = dialBlockedResult(request, "Call sharing is disabled for this PC."),
                            sequenceNumber = nextSequence(),
                        ),
                    )
                    return
                }
                val result = dialHandler.handle(request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_DIAL_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = if (result.success) {
                        "Dial request: ${result.detail}"
                    } else {
                        "Dial failed: ${result.detail}"
                    },
                )
                DebugEventLog.record("call", result.detail)
            }

            PacketType.PACKET_TYPE_TELEPHONY_DIAGNOSTICS_REQUEST -> {
                val request = com.linkable.protocol.v1.TelephonyDiagnosticsRequest.parseFrom(envelope.payload)
                if (!devicePermissionStore.permissionsFor(trustedDevice.deviceId).calls) {
                    DebugEventLog.record("call", "Telephony diagnostics blocked; call sharing is disabled for this PC.")
                    return
                }
                val result = telephonyDiagnosticsProvider.snapshot(request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_TELEPHONY_DIAGNOSTICS_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = "Telephony diagnostics sent",
                )
                DebugEventLog.record("call", "Telephony diagnostics: ${result.detail}")
            }

            PacketType.PACKET_TYPE_BLUETOOTH_ASSIST_DESKTOP_STATUS -> {
                val status = com.linkable.protocol.v1.BluetoothAssistDesktopStatus.parseFrom(envelope.payload)
                val result = bluetoothAssistHandler.handleDesktopStatus(status)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_BLUETOOTH_ASSIST_PHONE_STATUS,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = "Bluetooth status: ${result.detail}",
                )
                DebugEventLog.record("bluetooth", result.detail)
            }

            PacketType.PACKET_TYPE_SHARED_APP_LAUNCH_REQUEST -> {
                val request = com.linkable.protocol.v1.SharedAppLaunchRequest.parseFrom(envelope.payload)
                val result = handleSharedAppLaunch(trustedDevice, request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_SHARED_APP_LAUNCH_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("apps", result.detail)
            }

            PacketType.PACKET_TYPE_PHONE_FILE_LIST_REQUEST -> {
                val request = com.linkable.protocol.v1.PhoneFileListRequest.parseFrom(envelope.payload)
                val response = if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).fileBrowse) {
                    storageBrowser.list(request)
                } else {
                    phoneFileListBlocked(request, "Storage browsing is disabled for this PC.")
                }
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_PHONE_FILE_LIST_RESPONSE,
                        message = response,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("storage", response.detail)
            }

            PacketType.PACKET_TYPE_PHONE_FILE_PULL_REQUEST -> {
                val request = com.linkable.protocol.v1.PhoneFilePullRequest.parseFrom(envelope.payload)
                val permissions = devicePermissionStore.permissionsFor(trustedDevice.deviceId)
                val file = if (permissions.fileBrowse && permissions.files) storageBrowser.fileFor(request) else null
                val result = if (file == null) {
                    storageBrowser.pullResult(request, success = false, detail = "File is unavailable or file browsing/sharing is disabled.")
                } else {
                    storageBrowser.pullResult(request, success = true, detail = "Sending ${file.name} to desktop.")
                }
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_PHONE_FILE_PULL_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                if (file != null) {
                    phoneFileSender.sendFile(encrypted, file, ::nextSequence)
                }
                DebugEventLog.record("storage", result.detail)
            }

            PacketType.PACKET_TYPE_PHONE_CONTACTS_REQUEST -> {
                val request = com.linkable.protocol.v1.PhoneContactsRequest.parseFrom(envelope.payload)
                val response = if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).contacts) {
                    phoneContactsProvider.search(request)
                } else {
                    phoneContactsBlocked(request, "Contact sharing is disabled for this PC.")
                }
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_PHONE_CONTACTS_RESPONSE,
                        message = response,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("contacts", response.detail)
            }

            PacketType.PACKET_TYPE_PHONE_RECENT_CONTACTS_REQUEST -> {
                val request = com.linkable.protocol.v1.PhoneRecentContactsRequest.parseFrom(envelope.payload)
                val response = if (devicePermissionStore.permissionsFor(trustedDevice.deviceId).contacts) {
                    phoneContactsProvider.recents(request)
                } else {
                    recentContactsBlocked(request, "Contact sharing is disabled for this PC.")
                }
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_PHONE_RECENT_CONTACTS_RESPONSE,
                        message = response,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("contacts", response.detail)
            }

            PacketType.PACKET_TYPE_CAMERA_CAPABILITY_REQUEST -> {
                val request = com.linkable.protocol.v1.CameraCapabilityRequest.parseFrom(envelope.payload)
                val response = CameraStreamController.capabilitySnapshot(
                    context = appContext,
                    request = request,
                    cameraShareEnabled = true,
                )
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_CAMERA_CAPABILITY_RESPONSE,
                        message = response,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("camera", response.detail)
            }

            PacketType.PACKET_TYPE_CAMERA_STREAM_START_REQUEST -> {
                val request = com.linkable.protocol.v1.CameraStreamStartRequest.parseFrom(envelope.payload)
                val immediateResult = CameraStreamController.requestUserApproval(
                    context = appContext,
                    request = request,
                    cameraShareEnabled = true,
                    desktopName = trustedDevice.deviceName,
                    fallbackDesktopHost = desktopHost,
                )
                if (immediateResult != null) {
                    encrypted.writeEnvelope(
                        ConnectionIO.buildEnvelope(
                            packetType = PacketType.PACKET_TYPE_CAMERA_STREAM_START_RESULT,
                            message = immediateResult,
                            sequenceNumber = nextSequence(),
                        ),
                    )
                    DebugEventLog.record("camera", immediateResult.detail)
                } else {
                    CameraStreamingService.startForApproval(appContext, trustedDevice.deviceName)
                    openCameraApprovalUi()
                    DebugEventLog.record("camera", "Camera request shown for ${trustedDevice.deviceName}")
                }
            }

            PacketType.PACKET_TYPE_CAMERA_STREAM_ACK -> {
                val ack = com.linkable.protocol.v1.CameraStreamAck.parseFrom(envelope.payload)
                CameraStreamController.ack(ack.sessionToken)
            }

            PacketType.PACKET_TYPE_CAMERA_STREAM_STOP_REQUEST -> {
                val request = com.linkable.protocol.v1.CameraStreamStopRequest.parseFrom(envelope.payload)
                val result = CameraStreamController.stop(request)
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_CAMERA_STREAM_STOP_RESULT,
                        message = result,
                        sequenceNumber = nextSequence(),
                    ),
                )
                DebugEventLog.record("camera", result.detail)
            }

            else -> Unit
        }
    }

    private fun forwardNotificationEvent(
        encrypted: EncryptedConnection,
        trustedDevice: TrustedDevice,
        event: PhoneNotificationEvent,
    ) {
        when (event) {
            is PhoneNotificationEvent.Posted -> {
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_NOTIFICATION_POSTED,
                        message = event.notification,
                        sequenceNumber = nextSequence(),
                    ),
                )
                _state.value = PairingState.Success(
                    deviceName = trustedDevice.deviceName,
                    deviceId = trustedDevice.deviceId,
                    reusedTrust = true,
                    transportSummary = "Forwarded notification: ${event.notification.appName.ifBlank { event.notification.packageName }}",
                )
                DebugEventLog.record("notification", "Forwarded ${event.notification.appName.ifBlank { event.notification.packageName }}")
            }

            is PhoneNotificationEvent.Removed -> {
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_NOTIFICATION_REMOVED,
                        message = event.notification,
                        sequenceNumber = nextSequence(),
                    ),
                )
            }
        }
    }

    private fun shouldForwardNotificationToDevice(deviceId: String, event: PhoneNotificationEvent): Boolean {
        return when (event) {
            is PhoneNotificationEvent.Posted -> {
                val notification = event.notification
                if (notification.callLike) {
                    true
                } else {
                    !notificationBlocklistStore.isBlocked(deviceId, notification.packageName)
                }
            }

            is PhoneNotificationEvent.Removed -> true
        }
    }

    private fun notificationGateReason(
        permissions: com.linkable.trust.DevicePermissions,
        event: PhoneNotificationEvent,
    ): String? {
        return when (event) {
            is PhoneNotificationEvent.Posted -> {
                val postedAt = event.notification.postedAt.unixEpochMs
                if (postedAt > 0 && System.currentTimeMillis() - postedAt > MAX_NOTIFICATION_FORWARDING_AGE_MS) {
                    return "Notification was not forwarded; it is older than 30 minutes."
                }
                if (event.notification.callLike) {
                    if (permissions.calls) null else "Call-like notification was not forwarded; calls are disabled for this PC."
                } else {
                    if (permissions.notifications) null else "Notification was not forwarded; notifications are disabled for this PC."
                }
            }

            is PhoneNotificationEvent.Removed -> {
                if (permissions.calls || permissions.notifications) null else {
                    "Notification removal was not forwarded; calls and notifications are disabled for this PC."
                }
            }
        }
    }

    private fun logPermissionDrop(deviceId: String, feature: String, detail: String) {
        val now = System.currentTimeMillis()
        val key = "$deviceId:$feature:$detail"
        val previous = lastPermissionDropLogAt[key] ?: 0L
        if (now - previous < PERMISSION_DROP_LOG_INTERVAL_MS) return
        lastPermissionDropLogAt[key] = now
        DebugEventLog.record(feature, detail)
    }

    private fun forwardCallStateEvent(
        encrypted: EncryptedConnection,
        trustedDevice: TrustedDevice,
        event: com.linkable.protocol.v1.CallStateEvent,
    ) {
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_CALL_STATE_EVENT,
                message = event,
                sequenceNumber = nextSequence(),
            ),
        )
        _state.value = PairingState.Success(
            deviceName = trustedDevice.deviceName,
            deviceId = trustedDevice.deviceId,
            reusedTrust = true,
            transportSummary = "Forwarded call state: ${event.detail}",
        )
        DebugEventLog.record("call", "Forwarded call state: ${event.detail}")
    }

    private fun forwardCallMetadataEvent(
        encrypted: EncryptedConnection,
        trustedDevice: TrustedDevice,
        event: com.linkable.protocol.v1.CallMetadataEvent,
    ) {
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_CALL_METADATA_EVENT,
                message = event,
                sequenceNumber = nextSequence(),
            ),
        )
        _state.value = PairingState.Success(
            deviceName = trustedDevice.deviceName,
            deviceId = trustedDevice.deviceId,
            reusedTrust = true,
            transportSummary = "Forwarded call metadata: ${event.detail}",
        )
        DebugEventLog.record("call", "Forwarded call metadata: ${event.detail}")
    }

    private fun sendSharedAppsSnapshot(encrypted: EncryptedConnection, trustedDevice: TrustedDevice) {
        if (!devicePermissionStore.permissionsFor(trustedDevice.deviceId).sharedApps) return
        val snapshot = SharedAppsSnapshot.newBuilder()
            .setSnapshotId(UUID.randomUUID().toString())
            .addAllApps(installedAppsProvider.sharedShortcuts())
            .setGeneratedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_SHARED_APPS_SNAPSHOT,
                message = snapshot,
                sequenceNumber = nextSequence(),
            ),
        )
    }

    private fun handleSharedAppLaunch(
        trustedDevice: TrustedDevice,
        request: com.linkable.protocol.v1.SharedAppLaunchRequest,
    ): com.linkable.protocol.v1.SharedAppLaunchResult {
        val permissions = devicePermissionStore.permissionsFor(trustedDevice.deviceId)
        if (!permissions.sharedApps) {
            return sharedAppLaunchResult(request, false, "Shared Apps is disabled for this PC.")
        }
        val shared = installedAppsProvider.sharedShortcuts().any { it.packageName == request.packageName }
        if (!shared) {
            return sharedAppLaunchResult(request, false, "App is not shared from this phone.")
        }
        val intent = appContext.packageManager.getLaunchIntentForPackage(request.packageName)
            ?: return sharedAppLaunchResult(request, false, "No launchable activity found.")
        return runCatching {
            appContext.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            sharedAppLaunchResult(request, true, "Launched ${request.packageName}.")
        }.getOrElse { error ->
            sharedAppLaunchResult(request, false, error.message ?: "Launch failed.")
        }
    }

    private fun sharedAppLaunchResult(
        request: com.linkable.protocol.v1.SharedAppLaunchRequest,
        success: Boolean,
        detail: String,
    ): com.linkable.protocol.v1.SharedAppLaunchResult {
        return com.linkable.protocol.v1.SharedAppLaunchResult.newBuilder()
            .setRequestId(request.requestId)
            .setPackageName(request.packageName)
            .setSuccess(success)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun blockedFileTransferResult(transferId: String, detail: String): com.linkable.protocol.v1.FileTransferResult {
        return com.linkable.protocol.v1.FileTransferResult.newBuilder()
            .setTransferId(transferId)
            .setSuccess(false)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun callControlBlockedResult(
        request: com.linkable.protocol.v1.CallControlRequest,
        detail: String,
    ): com.linkable.protocol.v1.CallControlResult {
        return com.linkable.protocol.v1.CallControlResult.newBuilder()
            .setRequestId(request.requestId)
            .setAction(request.action)
            .setSuccess(false)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun dialBlockedResult(
        request: com.linkable.protocol.v1.DialRequest,
        detail: String,
    ): com.linkable.protocol.v1.DialResult {
        return com.linkable.protocol.v1.DialResult.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(false)
            .setDetail(detail)
            .setRequestedSimSlot(request.simSlot)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun phoneFileListBlocked(
        request: com.linkable.protocol.v1.PhoneFileListRequest,
        detail: String,
    ): com.linkable.protocol.v1.PhoneFileListResponse {
        return com.linkable.protocol.v1.PhoneFileListResponse.newBuilder()
            .setRequestId(request.requestId)
            .setPath(request.path)
            .setSuccess(false)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun phoneContactsBlocked(
        request: com.linkable.protocol.v1.PhoneContactsRequest,
        detail: String,
    ): com.linkable.protocol.v1.PhoneContactsResponse {
        return com.linkable.protocol.v1.PhoneContactsResponse.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(false)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun recentContactsBlocked(
        request: com.linkable.protocol.v1.PhoneRecentContactsRequest,
        detail: String,
    ): com.linkable.protocol.v1.PhoneRecentContactsResponse {
        return com.linkable.protocol.v1.PhoneRecentContactsResponse.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(false)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private suspend fun retryTrustedReconnect(device: DiscoveredDevice, trustedDevice: TrustedDevice, cause: Throwable) {
        if (!connectionAttemptInFlight.compareAndSet(false, true)) return
        try {
            reconnectTrustedWithBackoff(
                device = device,
                trustedDevice = trustedDevice,
                initialDetail = cause.message ?: "Encrypted session dropped",
            )
        } finally {
            connectionAttemptInFlight.set(false)
        }
    }

    private suspend fun reconnectTrustedWithBackoff(
        device: DiscoveredDevice,
        trustedDevice: TrustedDevice,
        initialDetail: String,
    ) {
        val delays = listOf(0L, 1_000L, 2_000L, 4_000L, 8_000L, 15_000L)
        delays.forEachIndexed { index, delayMs ->
            if (trustStore.get(trustedDevice.deviceId) == null) {
                _state.value = PairingState.Idle
                DebugEventLog.record("connection", "Stopped reconnecting because trust was removed")
                return
            }
            val attempt = index + 1
            _state.value = PairingState.Reconnecting(
                deviceName = trustedDevice.deviceName,
                attempt = attempt,
                detail = initialDetail,
            )
            if (delayMs > 0) {
                delay(delayMs)
            }
            if (safeAttemptTrustedReconnect(device, trustedDevice)) {
                return
            }
        }
        _state.value = PairingState.Error("Trusted desktop is not reachable yet. Linkable will keep scanning this LAN and reconnect automatically.")
    }

    private fun closePendingSession() {
        pendingSession?.let { session ->
            runCatching { session.socket.close() }
        }
        pendingSession = null
        pairingConfirmationInFlight.set(false)
    }

    private fun closeConnectingSocket() {
        connectingSocket?.let { socket -> runCatching { socket.close() } }
        connectingSocket = null
    }

    private fun closeActiveSession() {
        activeSessionJob?.cancel()
        activeSessionJob = null
        activeSocket?.let { socket -> runCatching { socket.close() } }
        activeSocket = null
        callStateMonitor.stop()
        PhoneClipboardMonitor.stop()
    }

    private fun updateClipboardMonitor(deviceId: String) {
        if (devicePermissionStore.permissionsFor(deviceId).forwardClipboardToPc) {
            PhoneClipboardMonitor.start(
                context = appContext,
                sourceDeviceId = identity.deviceId,
                sourceDeviceName = Build.MODEL ?: "Android Phone",
            )
        } else {
            PhoneClipboardMonitor.stop()
        }
    }

    private companion object {
        const val AUTO_RECONNECT_COOLDOWN_MS = 4_000L
        const val FALLBACK_RECONNECT_COOLDOWN_MS = 60_000L
        const val FALLBACK_CONNECT_TIMEOUT_MS = 350
        const val FALLBACK_NEARBY_HOST_RADIUS = 12
        const val ACTIVE_HEARTBEAT_INTERVAL_MS = 15_000L
        const val SHARED_APPS_SNAPSHOT_INTERVAL_MS = 300_000L
        const val PERMISSION_DROP_LOG_INTERVAL_MS = 15_000L
        const val MAX_NOTIFICATION_FORWARDING_AGE_MS = 30L * 60L * 1_000L
        const val MAX_LOCAL_EVENTS_PER_TICK = 32
        const val MAX_CAMERA_FRAMES_PER_TICK = 8
    }
}
