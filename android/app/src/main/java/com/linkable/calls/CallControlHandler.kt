package com.linkable.calls

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.telecom.TelecomManager
import androidx.core.content.ContextCompat
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.CallControlAction
import com.linkable.protocol.v1.CallControlRequest
import com.linkable.protocol.v1.CallControlResult
import com.linkable.protocol.v1.Timestamp

class CallControlHandler(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val telecomManager = appContext.getSystemService(TelecomManager::class.java)

    fun handle(request: CallControlRequest): CallControlResult {
        if (!hasAnswerCallsPermission()) {
            return result(request, success = false, detail = "ANSWER_PHONE_CALLS permission missing")
        }
        val outcome = runCatching {
            when (request.action) {
                CallControlAction.CALL_CONTROL_ACTION_ACCEPT -> acceptCall()
                CallControlAction.CALL_CONTROL_ACTION_REJECT -> endCall("reject call")
                CallControlAction.CALL_CONTROL_ACTION_HANGUP -> endCall("hang up call")
                else -> "unsupported call-control action: ${request.action}"
            }
        }.fold(
            onSuccess = { detail -> detail },
            onFailure = { error -> "call-control failed: ${error.message}" },
        )
        val success = !outcome.startsWith("unsupported") &&
            !outcome.startsWith("call-control failed") &&
            !outcome.contains("not executed")
        DebugEventLog.record("call", outcome)
        return result(request, success = success, detail = outcome)
    }

    @SuppressLint("MissingPermission")
    private fun acceptCall(): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return "accept call unsupported below Android 8"
        }
        telecomManager.acceptRingingCall()
        return "accept call requested"
    }

    @SuppressLint("MissingPermission")
    private fun endCall(label: String): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            return "$label unsupported below Android 9"
        }
        val ended = telecomManager.endCall()
        return if (ended) {
            "$label requested"
        } else {
            "$label not executed; no active supported call"
        }
    }

    private fun hasAnswerCallsPermission(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.ANSWER_PHONE_CALLS) == PackageManager.PERMISSION_GRANTED
    }

    private fun result(
        request: CallControlRequest,
        success: Boolean,
        detail: String,
    ): CallControlResult {
        return CallControlResult.newBuilder()
            .setRequestId(request.requestId)
            .setAction(request.action)
            .setSuccess(success)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }
}
