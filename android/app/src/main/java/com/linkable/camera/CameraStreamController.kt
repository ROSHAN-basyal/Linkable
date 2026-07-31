package com.linkable.camera

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.Image
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import android.util.Range
import android.util.Size
import androidx.core.content.ContextCompat
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.CameraCapabilityRequest
import com.linkable.protocol.v1.CameraCapabilityResponse
import com.linkable.protocol.v1.CameraCodec
import com.linkable.protocol.v1.CameraDeviceCapability
import com.linkable.protocol.v1.CameraFacing
import com.linkable.protocol.v1.CameraFrame
import com.linkable.protocol.v1.CameraProfile
import com.linkable.protocol.v1.CameraRoute
import com.linkable.protocol.v1.CameraStreamStartRequest
import com.linkable.protocol.v1.CameraStreamStartResult
import com.linkable.protocol.v1.CameraStreamStatusEvent
import com.linkable.protocol.v1.CameraStreamStopRequest
import com.linkable.protocol.v1.CameraStreamStopResult
import com.linkable.protocol.v1.Timestamp
import com.linkable.transport.SessionEventSignal
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.min

data class CameraSessionUiState(
    val pendingRequestId: String = "",
    val pendingDesktopName: String = "",
    val pendingRoute: CameraRoute = CameraRoute.CAMERA_ROUTE_UNSPECIFIED,
    val pendingFacing: CameraFacing = CameraFacing.CAMERA_FACING_UNSPECIFIED,
    val pendingWidth: Int = 0,
    val pendingHeight: Int = 0,
    val pendingFps: Int = 0,
    val activeSessionToken: String = "",
    val activeDesktopName: String = "",
    val activeRoute: CameraRoute = CameraRoute.CAMERA_ROUTE_UNSPECIFIED,
    val activeFacing: CameraFacing = CameraFacing.CAMERA_FACING_UNSPECIFIED,
    val activeWidth: Int = 0,
    val activeHeight: Int = 0,
    val activeFps: Int = 0,
    val framesSent: Long = 0,
    val detail: String = "Camera sharing is idle.",
) {
    val hasPendingRequest: Boolean get() = pendingRequestId.isNotBlank()
    val isActive: Boolean get() = activeSessionToken.isNotBlank()
    val keepScreenAwake: Boolean get() = hasPendingRequest || isActive
}

object CameraStreamController {
    val statusEvents: Channel<CameraStreamStatusEvent> = Channel(capacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val frameEvents: Channel<CameraFrame> = Channel(Channel.CONFLATED)

    private const val STREAM_MAGIC = "LINKABLE_CAMERA_MJPEG_V1\n"
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Any()
    private val _uiState = MutableStateFlow(CameraSessionUiState())
    private var activeSession: CameraSession? = null
    private var pendingStart: PendingCameraStart? = null

    val uiState: StateFlow<CameraSessionUiState> = _uiState.asStateFlow()

    private data class PendingCameraStart(
        val request: CameraStreamStartRequest,
        val desktopName: String,
        val fallbackDesktopHost: String,
    )

    fun capabilitySnapshot(
        context: Context,
        request: CameraCapabilityRequest,
        cameraShareEnabled: Boolean,
    ): CameraCapabilityResponse {
        val permissionGranted = hasCameraPermission(context)
        val builder = CameraCapabilityResponse.newBuilder()
            .setRequestId(request.requestId)
            .setCameraPermissionGranted(permissionGranted)
            .setCameraShareEnabled(cameraShareEnabled)
            .setCompletedAt(now())
        if (!permissionGranted) {
            return builder
                .setSuccess(false)
                .setDetail("Camera permission is not granted.")
                .build()
        }
        runCatching {
            val manager = context.getSystemService(CameraManager::class.java)
            manager.cameraIdList.forEach { cameraId ->
                builder.addCameras(cameraCapability(manager, cameraId))
            }
        }.onFailure { error ->
            return builder
                .setSuccess(false)
                .setDetail(error.message ?: "Camera capability query failed.")
                .build()
        }
        return builder
            .setSuccess(cameraShareEnabled)
            .setDetail(
                if (cameraShareEnabled) {
                    "Camera sharing is ready; ${builder.camerasCount} camera(s) available."
                } else {
                    "Camera sharing is disabled for this PC."
                },
            )
            .build()
    }

    fun start(
        context: Context,
        request: CameraStreamStartRequest,
        cameraShareEnabled: Boolean,
        fallbackDesktopHost: String,
    ): CameraStreamStartResult {
        if (!cameraShareEnabled) {
            return startResult(request, false, "Camera sharing is disabled for this PC.")
        }
        if (!hasCameraPermission(context)) {
            return startResult(request, false, "Camera permission is not granted.")
        }
        val sessionTransport = request.route == CameraRoute.CAMERA_ROUTE_LAN && request.endpointPort <= 0
        val host = if (sessionTransport) "" else request.endpointHost.ifBlank { fallbackDesktopHost }
        if (!sessionTransport && (host.isBlank() || request.endpointPort <= 0)) {
            return startResult(request, false, "Desktop camera stream endpoint is missing.")
        }
        val manager = context.getSystemService(CameraManager::class.java)
        val selection = runCatching { selectCamera(manager, request.facing, request.width, request.height) }.getOrElse { error ->
            return startResult(request, false, error.message ?: "No usable camera was found.")
        }
        synchronized(lock) {
            activeSession?.stop("replaced by new camera stream")
            drainPendingEvents()
            val session = CameraSession(
                context = context.applicationContext,
                manager = manager,
                request = request,
                host = host,
                sessionTransport = sessionTransport,
                cameraId = selection.cameraId,
                size = selection.size,
            )
            activeSession = session
            session.start()
        }
        CameraStreamingService.startActive(context)
        DebugEventLog.record("camera", "Camera stream requested over ${request.route}: ${selection.size.width}x${selection.size.height}")
        _uiState.value = CameraSessionUiState(
            activeSessionToken = request.sessionToken,
            activeDesktopName = _uiState.value.pendingDesktopName,
            activeRoute = request.route,
            activeFacing = request.facing,
            activeWidth = selection.size.width,
            activeHeight = selection.size.height,
            activeFps = request.fps,
            detail = "Camera stream accepted; connecting to desktop receiver.",
        )
        return startResult(
            request = request,
            success = true,
            detail = "Camera stream accepted; connecting to desktop receiver.",
            width = selection.size.width,
            height = selection.size.height,
            host = host,
        )
    }

    fun requestUserApproval(
        context: Context,
        request: CameraStreamStartRequest,
        cameraShareEnabled: Boolean,
        desktopName: String,
        fallbackDesktopHost: String,
    ): CameraStreamStartResult? {
        if (!cameraShareEnabled) {
            return startResult(request, false, "Camera sharing is disabled for this PC.")
        }
        if (!hasCameraPermission(context)) {
            return startResult(request, false, "Camera permission is not granted.")
        }
        val sessionTransport = request.route == CameraRoute.CAMERA_ROUTE_LAN && request.endpointPort <= 0
        val host = if (sessionTransport) "" else request.endpointHost.ifBlank { fallbackDesktopHost }
        if (!sessionTransport && (host.isBlank() || request.endpointPort <= 0)) {
            return startResult(request, false, "Desktop camera stream endpoint is missing.")
        }
        val manager = context.getSystemService(CameraManager::class.java)
        val selection = runCatching { selectCamera(manager, request.facing, request.width, request.height) }.getOrElse { error ->
            return startResult(request, false, error.message ?: "No usable camera was found.")
        }
        synchronized(lock) {
            pendingStart = PendingCameraStart(request, desktopName, fallbackDesktopHost)
            _uiState.value = CameraSessionUiState(
                pendingRequestId = request.requestId,
                pendingDesktopName = desktopName,
                pendingRoute = request.route,
                pendingFacing = request.facing,
                pendingWidth = selection.size.width,
                pendingHeight = selection.size.height,
                pendingFps = request.fps,
                detail = "$desktopName requests camera access.",
            )
        }
        DebugEventLog.record("camera", "Camera request from $desktopName is waiting for phone approval")
        return null
    }

    fun approvePending(context: Context): CameraStreamStartResult? {
        val pending = synchronized(lock) {
            val value = pendingStart ?: return null
            pendingStart = null
            _uiState.value = _uiState.value.copy(detail = "Starting camera stream for ${value.desktopName}...")
            value
        }
        return start(
            context = context,
            request = pending.request,
            cameraShareEnabled = true,
            fallbackDesktopHost = pending.fallbackDesktopHost,
        )
    }

    fun rejectPending(reason: String = "Phone user rejected camera sharing."): CameraStreamStartResult? {
        val pending = synchronized(lock) {
            val value = pendingStart ?: return null
            pendingStart = null
            _uiState.value = CameraSessionUiState(detail = reason)
            value
        }
        DebugEventLog.record("camera", reason)
        return startResult(pending.request, false, reason)
    }

    fun ack(sessionToken: String) {
        synchronized(lock) {
            activeSession?.takeIf { it.token == sessionToken }?.markAck()
        }
    }

    fun stop(request: CameraStreamStopRequest): CameraStreamStopResult {
        val pendingCancelled = synchronized(lock) {
            val pending = pendingStart
            if (pending != null && (request.sessionToken.isBlank() || pending.request.sessionToken == request.sessionToken)) {
                pendingStart = null
                _uiState.value = CameraSessionUiState(detail = request.reason.ifBlank { "Desktop cancelled camera request." })
                true
            } else {
                false
            }
        }
        if (pendingCancelled) {
            return CameraStreamStopResult.newBuilder()
                .setRequestId(request.requestId)
                .setSessionToken(request.sessionToken)
                .setSuccess(true)
                .setDetail("Pending camera request was cancelled.")
                .setStoppedAt(now())
                .build()
        }
        val stopped = synchronized(lock) {
            val session = activeSession
            if (session != null && (request.sessionToken.isBlank() || session.token == request.sessionToken)) {
                session.stop(request.reason.ifBlank { "desktop requested stop" })
                activeSession = null
                drainPendingEvents()
                _uiState.value = CameraSessionUiState(detail = "Camera stream stopped by desktop.")
                true
            } else {
                false
            }
        }
        return CameraStreamStopResult.newBuilder()
            .setRequestId(request.requestId)
            .setSessionToken(request.sessionToken)
            .setSuccess(true)
            .setDetail(if (stopped) "Camera stream stopped." else "No matching camera stream was active.")
            .setStoppedAt(now())
            .build()
    }

    fun stopAny(reason: String) {
        synchronized(lock) {
            pendingStart = null
            activeSession?.stop(reason)
            activeSession = null
            drainPendingEvents()
            _uiState.value = CameraSessionUiState(detail = reason)
        }
    }

    private fun drainPendingEvents() {
        while (statusEvents.tryReceive().isSuccess) Unit
        while (frameEvents.tryReceive().isSuccess) Unit
    }

    private fun hasCameraPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    }

    private fun cameraCapability(manager: CameraManager, cameraId: String): CameraDeviceCapability {
        val characteristics = manager.getCameraCharacteristics(cameraId)
        val facing = when (characteristics.get(CameraCharacteristics.LENS_FACING)) {
            CameraCharacteristics.LENS_FACING_FRONT -> CameraFacing.CAMERA_FACING_FRONT
            CameraCharacteristics.LENS_FACING_BACK -> CameraFacing.CAMERA_FACING_BACK
            else -> CameraFacing.CAMERA_FACING_UNSPECIFIED
        }
        val profiles = outputSizes(characteristics).take(6).map { size ->
            CameraProfile.newBuilder()
                .setWidth(size.width)
                .setHeight(size.height)
                .setFps(safeFps(characteristics))
                .setCodec(CameraCodec.CAMERA_CODEC_MJPEG)
                .setLabel("${size.width}x${size.height} MJPEG")
                .build()
        }
        return CameraDeviceCapability.newBuilder()
            .setCameraId(cameraId)
            .setFacing(facing)
            .setFlashAvailable(characteristics.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true)
            .addAllFocusModes(focusModes(characteristics))
            .addAllProfiles(profiles)
            .build()
    }

    private fun outputSizes(characteristics: CameraCharacteristics): List<Size> {
        val sizes = characteristics
            .get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
            ?.getOutputSizes(ImageFormat.YUV_420_888)
            ?.toList()
            .orEmpty()
        val preferred = listOf(Size(1280, 720), Size(960, 540), Size(640, 480), Size(640, 360), Size(320, 240))
        val exact = preferred.filter { target -> sizes.any { it.width == target.width && it.height == target.height } }
        val fallback = sizes
            .filter { it.width <= 1920 && it.height <= 1080 }
            .sortedByDescending { it.width * it.height }
        return (exact + fallback).distinctBy { "${it.width}x${it.height}" }
    }

    private fun focusModes(characteristics: CameraCharacteristics): List<String> {
        return (characteristics.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES) ?: intArrayOf()).map { mode ->
            when (mode) {
                CaptureRequest.CONTROL_AF_MODE_AUTO -> "auto"
                CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO -> "continuous_video"
                CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE -> "continuous_picture"
                CaptureRequest.CONTROL_AF_MODE_EDOF -> "fixed"
                CaptureRequest.CONTROL_AF_MODE_MACRO -> "macro"
                CaptureRequest.CONTROL_AF_MODE_OFF -> "fixed"
                else -> "unspecified"
            }
        }.distinct()
    }

    private fun safeFps(characteristics: CameraCharacteristics): Int {
        val ranges = characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES).orEmpty()
        return ranges.maxOfOrNull { it.upper.coerceAtMost(30) } ?: 12
    }

    private fun selectCamera(
        manager: CameraManager,
        requestedFacing: CameraFacing,
        requestedWidth: Int,
        requestedHeight: Int,
    ): CameraSelection {
        val candidates = manager.cameraIdList.map { cameraId ->
            val characteristics = manager.getCameraCharacteristics(cameraId)
            cameraId to characteristics
        }
        val requestedLens = when (requestedFacing) {
            CameraFacing.CAMERA_FACING_FRONT -> CameraCharacteristics.LENS_FACING_FRONT
            CameraFacing.CAMERA_FACING_BACK -> CameraCharacteristics.LENS_FACING_BACK
            else -> null
        }
        val selected = candidates.firstOrNull { (_, characteristics) ->
            requestedLens == null || characteristics.get(CameraCharacteristics.LENS_FACING) == requestedLens
        } ?: candidates.firstOrNull() ?: throw IllegalStateException("No camera is available.")
        val size = chooseSize(outputSizes(selected.second), requestedWidth, requestedHeight)
        return CameraSelection(selected.first, size)
    }

    private fun chooseSize(sizes: List<Size>, requestedWidth: Int, requestedHeight: Int): Size {
        if (sizes.isEmpty()) return Size(640, 480)
        val width = requestedWidth.takeIf { it > 0 } ?: 640
        val height = requestedHeight.takeIf { it > 0 } ?: 480
        return sizes.minBy { abs(it.width - width) + abs(it.height - height) }
    }

    private fun startResult(
        request: CameraStreamStartRequest,
        success: Boolean,
        detail: String,
        width: Int = request.width,
        height: Int = request.height,
        host: String = request.endpointHost,
    ): CameraStreamStartResult {
        return CameraStreamStartResult.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(success)
            .setDetail(detail)
            .setRoute(request.route)
            .setFacing(request.facing)
            .setCodec(CameraCodec.CAMERA_CODEC_MJPEG)
            .setWidth(width)
            .setHeight(height)
            .setFps(request.fps)
            .setEndpointHost(host)
            .setEndpointPort(request.endpointPort)
            .setSessionToken(request.sessionToken)
            .setStartedAt(now())
            .build()
    }

    private fun now(): Timestamp {
        return Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build()
    }

    private data class CameraSelection(val cameraId: String, val size: Size)

    private class CameraSession(
        private val context: Context,
        private val manager: CameraManager,
        private val request: CameraStreamStartRequest,
        private val host: String,
        private val sessionTransport: Boolean,
        private val cameraId: String,
        private val size: Size,
    ) {
        val token: String = request.sessionToken
        private val stopped = AtomicBoolean(false)
        private val thread = HandlerThread("LinkableCameraStream")
        private lateinit var handler: Handler
        private var imageReader: ImageReader? = null
        private var cameraDevice: CameraDevice? = null
        private var captureSession: CameraCaptureSession? = null
        private var socket: Socket? = null
        private var output: DataOutputStream? = null
        private var framesSent: Long = 0
        private var frameSequence: Long = 0
        private var lastFrameAtMs: Long = 0
        @Volatile private var lastAckAtMs: Long = System.currentTimeMillis()

        fun start() {
            thread.start()
            handler = Handler(thread.looper)
            scope.launch {
                try {
                    if (!sessionTransport) {
                        connectSocket()
                    }
                    openCamera()
                    startWatchdog()
                    startStatusLoop()
                } catch (error: Throwable) {
                    DebugEventLog.record("camera", "Camera stream failed: ${error.message}")
                    stop(error.message ?: "camera stream failed")
                }
            }
        }

        fun markAck() {
            lastAckAtMs = System.currentTimeMillis()
        }

        fun stop(reason: String) {
            if (!stopped.compareAndSet(false, true)) return
            runCatching { captureSession?.close() }
            runCatching { cameraDevice?.close() }
            runCatching { imageReader?.close() }
            runCatching { socket?.close() }
            if (::handler.isInitialized) {
                handler.post { thread.quitSafely() }
            } else {
                thread.quitSafely()
            }
            if (statusEvents.trySend(statusEvent(active = false, detail = reason)).isSuccess) {
                SessionEventSignal.notifyPendingWork()
            }
            DebugEventLog.record("camera", "Camera stream stopped: $reason")
        }

        @SuppressLint("MissingPermission")
        private fun openCamera() {
            imageReader = ImageReader.newInstance(size.width, size.height, ImageFormat.YUV_420_888, 2).apply {
                setOnImageAvailableListener({ reader ->
                    val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
                    image.use { processFrame(it) }
                }, handler)
            }
            manager.openCamera(
                cameraId,
                object : CameraDevice.StateCallback() {
                    override fun onOpened(camera: CameraDevice) {
                        cameraDevice = camera
                        createCaptureSession(camera)
                    }

                    override fun onDisconnected(camera: CameraDevice) {
                        stop("camera disconnected")
                    }

                    override fun onError(camera: CameraDevice, error: Int) {
                        stop("camera error $error")
                    }
                },
                handler,
            )
        }

        private fun createCaptureSession(camera: CameraDevice) {
            val reader = imageReader ?: return
            camera.createCaptureSession(
                listOf(reader.surface),
                object : CameraCaptureSession.StateCallback() {
                    override fun onConfigured(session: CameraCaptureSession) {
                        captureSession = session
                        val builder = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                            addTarget(reader.surface)
                            set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
                            focusMode()?.let { set(CaptureRequest.CONTROL_AF_MODE, it) }
                            set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
                            set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_AUTO)
                            fpsRange()?.let { set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, it) }
                        }
                        session.setRepeatingRequest(builder.build(), null, handler)
                        if (statusEvents.trySend(statusEvent(active = true, detail = "camera opened; waiting for frames")).isSuccess) {
                            SessionEventSignal.notifyPendingWork()
                        }
                    }

                    override fun onConfigureFailed(session: CameraCaptureSession) {
                        stop("camera capture session failed")
                    }
                },
                handler,
            )
        }

        private fun connectSocket() {
            val streamSocket = Socket()
            streamSocket.connect(InetSocketAddress(host, request.endpointPort), 5_000)
            val out = DataOutputStream(streamSocket.getOutputStream())
            val tokenBytes = token.toByteArray(Charsets.UTF_8)
            out.write(STREAM_MAGIC.toByteArray(Charsets.US_ASCII))
            out.writeShort(tokenBytes.size)
            out.write(tokenBytes)
            out.flush()
            socket = streamSocket
            output = out
        }

        private fun processFrame(image: Image) {
            if (stopped.get()) return
            val now = System.currentTimeMillis()
            val frameGap = 1_000L / maxOf(1, request.fps)
            if (now - lastFrameAtMs < frameGap) return
            lastFrameAtMs = now
            val jpeg = yuvToJpeg(image, request.jpegQuality.takeIf { it > 0 } ?: 72)
            if (jpeg.isEmpty()) {
                DebugEventLog.record("camera", "Skipped empty camera JPEG frame")
                return
            }
            if (sessionTransport) {
                val frame = CameraFrame.newBuilder()
                    .setSessionToken(token)
                    .setFrameSequence(++frameSequence)
                    .setCodec(CameraCodec.CAMERA_CODEC_MJPEG)
                    .setWidth(size.width)
                    .setHeight(size.height)
                    .setFrameBytes(com.google.protobuf.ByteString.copyFrom(jpeg))
                    .setCapturedAt(now())
                    .build()
                if (frameEvents.trySend(frame).isSuccess) {
                    framesSent += 1
                    SessionEventSignal.notifyPendingWork()
                }
                return
            }
            val out = output ?: return
            runCatching {
                synchronized(out) {
                    out.writeInt(jpeg.size)
                    out.write(jpeg)
                    out.flush()
                }
                framesSent += 1
            }.onFailure { error ->
                stop(error.message ?: "desktop camera receiver closed")
            }
        }

        private fun fpsRange(): Range<Int>? {
            val characteristics = runCatching { manager.getCameraCharacteristics(cameraId) }.getOrNull() ?: return null
            val ranges = characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES).orEmpty()
            val target = request.fps.takeIf { it > 0 } ?: 12
            return ranges
                .filter { it.lower <= target && it.upper >= target }
                .minByOrNull { it.upper - it.lower }
                ?: ranges.minByOrNull { abs(it.upper - target) }
        }

        private fun focusMode(): Int? {
            val characteristics = runCatching { manager.getCameraCharacteristics(cameraId) }.getOrNull() ?: return null
            val modes = characteristics.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES) ?: intArrayOf()
            return when {
                CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO in modes -> CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO
                CaptureRequest.CONTROL_AF_MODE_AUTO in modes -> CaptureRequest.CONTROL_AF_MODE_AUTO
                CaptureRequest.CONTROL_AF_MODE_OFF in modes -> CaptureRequest.CONTROL_AF_MODE_OFF
                else -> null
            }
        }

        private fun startWatchdog() {
            val timeout = request.ackTimeoutMs.takeIf { it > 0 }?.toLong() ?: 7_000L
            scope.launch {
                while (!stopped.get()) {
                    delay(1_000L)
                    if (System.currentTimeMillis() - lastAckAtMs > timeout) {
                        stop("desktop ACK timeout")
                    }
                }
            }
        }

        private fun startStatusLoop() {
            scope.launch {
                while (!stopped.get()) {
                    delay(3_000L)
                    if (statusEvents.trySend(statusEvent(active = true, detail = "streaming ${size.width}x${size.height}")).isSuccess) {
                        SessionEventSignal.notifyPendingWork()
                    }
                }
            }
        }

        private fun statusEvent(active: Boolean, detail: String): CameraStreamStatusEvent {
            val nextFrames = framesSent
            val current = _uiState.value
            if (current.activeSessionToken == token) {
                _uiState.value = if (active) {
                    current.copy(detail = detail, framesSent = nextFrames)
                } else {
                    CameraSessionUiState(detail = detail)
                }
            }
            return CameraStreamStatusEvent.newBuilder()
                .setSessionToken(token)
                .setActive(active)
                .setDetail(detail)
                .setFramesSent(nextFrames)
                .setGeneratedAt(now())
                .build()
        }

        private fun yuvToJpeg(image: Image, quality: Int): ByteArray {
            val crop = image.cropRect
            val width = crop.width()
            val height = crop.height()
            if (width <= 0 || height <= 0) return ByteArray(0)
            val nv21 = yuv420888ToNv21(image, crop, width, height)
            val yuvImage = YuvImage(nv21, ImageFormat.NV21, width, height, null)
            val output = ByteArrayOutputStream()
            val ok = yuvImage.compressToJpeg(Rect(0, 0, width, height), quality.coerceIn(30, 95), output)
            return if (ok) output.toByteArray() else ByteArray(0)
        }

        private fun yuv420888ToNv21(image: Image, crop: Rect, width: Int, height: Int): ByteArray {
            val output = ByteArray(width * height * 3 / 2)
            output.fill(128.toByte(), width * height, output.size)
            copyPlane(
                plane = image.planes[0],
                crop = crop,
                width = width,
                height = height,
                output = output,
                outputOffsetStart = 0,
                outputPixelStride = 1,
            )
            val chromaCrop = Rect(crop.left / 2, crop.top / 2, crop.right / 2, crop.bottom / 2)
            val chromaWidth = width / 2
            val chromaHeight = height / 2
            copyPlane(
                plane = image.planes[2],
                crop = chromaCrop,
                width = chromaWidth,
                height = chromaHeight,
                output = output,
                outputOffsetStart = width * height,
                outputPixelStride = 2,
            )
            copyPlane(
                plane = image.planes[1],
                crop = chromaCrop,
                width = chromaWidth,
                height = chromaHeight,
                output = output,
                outputOffsetStart = width * height + 1,
                outputPixelStride = 2,
            )
            return output
        }

        private fun copyPlane(
            plane: Image.Plane,
            crop: Rect,
            width: Int,
            height: Int,
            output: ByteArray,
            outputOffsetStart: Int,
            outputPixelStride: Int,
        ) {
            if (width <= 0 || height <= 0) return
            val buffer = plane.buffer.duplicate()
            val rowStride = plane.rowStride
            val pixelStride = plane.pixelStride
            val rowData = ByteArray(rowStride.coerceAtLeast(width * pixelStride))
            var outputOffset = outputOffsetStart
            for (row in 0 until height) {
                val rowStart = rowStride * (crop.top + row) + pixelStride * crop.left
                if (rowStart >= buffer.limit()) return
                buffer.position(rowStart.coerceAtMost(buffer.limit()))
                val bytesInRow = if (pixelStride == 1 && outputPixelStride == 1) {
                    width
                } else {
                    (width - 1) * pixelStride + 1
                }
                val available = min(bytesInRow, buffer.remaining())
                if (available <= 0) return
                if (pixelStride == 1 && outputPixelStride == 1) {
                    val bytesToCopy = min(width, available)
                    buffer.get(output, outputOffset, bytesToCopy)
                    outputOffset += width
                    continue
                }
                buffer.get(rowData, 0, available)
                for (col in 0 until width) {
                    val sourceIndex = col * pixelStride
                    if (sourceIndex < available && outputOffset < output.size) {
                        output[outputOffset] = rowData[sourceIndex]
                    }
                    outputOffset += outputPixelStride
                }
            }
        }
    }
}
