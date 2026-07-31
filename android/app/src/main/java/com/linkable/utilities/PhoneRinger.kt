package com.linkable.utilities

import android.content.Context
import android.media.AudioAttributes
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.RingPhoneAction
import com.linkable.protocol.v1.RingPhoneRequest
import com.linkable.protocol.v1.RingPhoneResult
import com.linkable.protocol.v1.Timestamp

class PhoneRinger(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private var ringtone: Ringtone? = null
    private var ringing = false
    private val autoStop = Runnable {
        synchronized(this) {
            stopInternal()
            DebugEventLog.record("utility", "Ring phone stopped after timeout")
        }
    }

    fun handle(request: RingPhoneRequest): RingPhoneResult {
        return synchronized(this) {
            when (request.action) {
                RingPhoneAction.RING_PHONE_ACTION_START -> {
                    val detail = startInternal(request.durationMs.toLong())
                    result(request, success = true, detail = detail, ringing = ringing)
                }

                RingPhoneAction.RING_PHONE_ACTION_STOP -> {
                    stopInternal()
                    DebugEventLog.record("utility", "Stopped phone ring from desktop")
                    result(request, success = true, detail = "ring stopped", ringing = false)
                }

                else -> result(
                    request = request,
                    success = false,
                    detail = "unsupported ring action: ${request.action}",
                    ringing = ringing,
                )
            }
        }
    }

    private fun startInternal(requestedDurationMs: Long): String {
        stopInternal()
        val durationMs = requestedDurationMs.coerceIn(1_000L, 60_000L)
        val toneUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        if (toneUri == null) {
            ringing = false
            return "no system tone available"
        }
        val nextRingtone = RingtoneManager.getRingtone(appContext, toneUri)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            nextRingtone.audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
        }
        ringtone = nextRingtone
        runCatching { nextRingtone.play() }
        startVibration()
        ringing = true
        handler.postDelayed(autoStop, durationMs)
        DebugEventLog.record("utility", "Ringing phone for ${durationMs / 1000}s from desktop")
        return "ringing phone for ${durationMs / 1000}s"
    }

    private fun stopInternal() {
        handler.removeCallbacks(autoStop)
        runCatching { ringtone?.stop() }
        ringtone = null
        runCatching { vibrator()?.cancel() }
        ringing = false
    }

    private fun startVibration() {
        val vibrator = vibrator() ?: return
        if (!vibrator.hasVibrator()) return
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 700, 300), 0))
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(longArrayOf(0, 700, 300), 0)
            }
        }
    }

    private fun vibrator(): Vibrator? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            appContext.getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            appContext.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
    }

    private fun result(
        request: RingPhoneRequest,
        success: Boolean,
        detail: String,
        ringing: Boolean,
    ): RingPhoneResult {
        return RingPhoneResult.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(success)
            .setDetail(detail)
            .setRinging(ringing)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }
}
