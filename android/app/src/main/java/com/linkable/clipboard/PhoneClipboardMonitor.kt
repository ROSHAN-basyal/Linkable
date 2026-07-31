package com.linkable.clipboard

import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.ClipboardUpdate
import com.linkable.protocol.v1.Timestamp
import com.linkable.transport.SessionEventSignal
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import java.security.MessageDigest
import java.util.UUID

object PhoneClipboardMonitor {
    val events: Channel<ClipboardUpdate> = Channel(capacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)

    private const val MAX_TEXT_CHARS = 8_192
    private val mainHandler = Handler(Looper.getMainLooper())
    private val lock = Any()
    private var started = false
    private var lastFingerprint = ""
    private var clipboardManager: ClipboardManager? = null
    private var clipboardListener: ClipboardManager.OnPrimaryClipChangedListener? = null

    fun start(context: Context, sourceDeviceId: String, sourceDeviceName: String) {
        val appContext = context.applicationContext
        val clipboard = appContext.getSystemService(ClipboardManager::class.java)
        val listener = ClipboardManager.OnPrimaryClipChangedListener {
            emitCurrentClipboard(appContext, clipboard, sourceDeviceId, sourceDeviceName)
        }
        synchronized(lock) {
            if (started) return
            started = true
            clipboardManager = clipboard
            clipboardListener = listener
        }
        mainHandler.post {
            val stillRequested = synchronized(lock) {
                started && clipboardListener === listener
            }
            if (!stillRequested) return@post
            runCatching {
                clipboard.addPrimaryClipChangedListener(listener)
                DebugEventLog.record("clipboard", "Mobile clipboard monitor active")
            }.onFailure { error ->
                synchronized(lock) {
                    started = false
                }
                DebugEventLog.record("clipboard", "Clipboard monitor failed: ${error.message}")
            }
        }
    }

    fun stop() {
        val manager: ClipboardManager?
        val listener: ClipboardManager.OnPrimaryClipChangedListener?
        synchronized(lock) {
            if (!started) return
            started = false
            manager = clipboardManager
            listener = clipboardListener
            clipboardManager = null
            clipboardListener = null
        }
        if (manager != null && listener != null) {
            mainHandler.post {
                runCatching { manager.removePrimaryClipChangedListener(listener) }
                DebugEventLog.record("clipboard", "Mobile clipboard monitor stopped")
            }
        }
    }

    private fun emitCurrentClipboard(
        context: Context,
        clipboard: ClipboardManager,
        sourceDeviceId: String,
        sourceDeviceName: String,
    ) {
        val text = runCatching {
            val clip = clipboard.primaryClip ?: return
            val description = clipboard.primaryClipDescription
            if (description != null && !description.hasMimeType(ClipDescription.MIMETYPE_TEXT_PLAIN) &&
                !description.hasMimeType(ClipDescription.MIMETYPE_TEXT_HTML)
            ) {
                return
            }
            clip.getItemAt(0)?.coerceToText(context)?.toString().orEmpty()
        }.getOrElse { error ->
            DebugEventLog.record("clipboard", "Clipboard read failed: ${error.message}")
            return
        }.trim()
        if (text.isBlank()) return
        val bounded = text.take(MAX_TEXT_CHARS)
        val fingerprint = sha256(bounded)
        synchronized(lock) {
            if (fingerprint == lastFingerprint) return
            lastFingerprint = fingerprint
        }
        val now = System.currentTimeMillis()
        val update = ClipboardUpdate.newBuilder()
            .setUpdateId(UUID.randomUUID().toString())
            .setText(bounded)
            .setMimeType("text/plain")
            .setTextLength(bounded.length)
            .setUpdatedAt(Timestamp.newBuilder().setUnixEpochMs(now).build())
            .setSourceDeviceId(sourceDeviceId)
            .setSourceDeviceName(sourceDeviceName)
            .build()
        if (events.trySend(update).isSuccess) {
            SessionEventSignal.notifyPendingWork()
            DebugEventLog.record("clipboard", "Queued mobile clipboard update (${bounded.length} chars)")
        }
    }

    private fun sha256(value: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte) }
    }
}
