package com.linkable.calls

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.telephony.SubscriptionInfo
import android.telephony.SubscriptionManager
import android.telephony.PhoneStateListener
import android.telephony.TelephonyManager
import androidx.core.content.ContextCompat
import com.linkable.debug.DebugEventLog
import com.linkable.notifications.AppCallActivityTracker
import com.linkable.protocol.v1.CallDirection
import com.linkable.protocol.v1.CallMetadataEvent
import com.linkable.protocol.v1.CallSourceType
import com.linkable.protocol.v1.CallStateEvent
import com.linkable.protocol.v1.PhoneAudioRouteType
import com.linkable.protocol.v1.PhoneCallState
import com.linkable.protocol.v1.Timestamp
import java.util.UUID

class CallStateMonitor(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private val telephonyManager = appContext.getSystemService(TelephonyManager::class.java)
    private val subscriptionManager = appContext.getSystemService(SubscriptionManager::class.java)
    private val audioManager = appContext.getSystemService(AudioManager::class.java)
    private var registered = false
    private var lastState: PhoneCallState? = null
    private var lastDirection: CallDirection = CallDirection.CALL_DIRECTION_UNSPECIFIED
    private var lastCallerId: String = ""
    private var suppressingAppCallTelephony = false
    private var pendingAmbiguousTelephonyState: Runnable? = null

    private val listener = object : PhoneStateListener() {
        @Deprecated("Deprecated Android callback still supports this minSdk range.")
        override fun onCallStateChanged(state: Int, phoneNumber: String?) {
            val callState = when (state) {
                TelephonyManager.CALL_STATE_IDLE -> PhoneCallState.PHONE_CALL_STATE_IDLE
                TelephonyManager.CALL_STATE_RINGING -> PhoneCallState.PHONE_CALL_STATE_RINGING
                TelephonyManager.CALL_STATE_OFFHOOK -> PhoneCallState.PHONE_CALL_STATE_OFFHOOK
                else -> PhoneCallState.PHONE_CALL_STATE_UNSPECIFIED
            }
            handleTelephonyState(callState, phoneNumber)
        }
    }

    fun start() {
        if (ContextCompat.checkSelfPermission(appContext, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            DebugEventLog.record("call", "READ_PHONE_STATE permission missing; call mirroring disabled")
            return
        }
        mainHandler.post {
            if (registered) return@post
            runCatching {
                telephonyManager.listen(listener, PhoneStateListener.LISTEN_CALL_STATE)
                registered = true
                DebugEventLog.record("call", "Call-state monitor active")
            }.onFailure { error ->
                DebugEventLog.record("call", "Call-state monitor failed: ${error.message}")
            }
        }
    }

    fun stop() {
        mainHandler.post {
            if (!registered) return@post
            runCatching {
                telephonyManager.listen(listener, PhoneStateListener.LISTEN_NONE)
            }
            registered = false
            lastState = null
            cancelPendingAmbiguousTelephony()
        }
    }

    private fun handleTelephonyState(state: PhoneCallState, phoneNumber: String?) {
        if (state == PhoneCallState.PHONE_CALL_STATE_IDLE) {
            val hadPendingAmbiguousState = pendingAmbiguousTelephonyState != null
            cancelPendingAmbiguousTelephony()
            if (hadPendingAmbiguousState && AppCallActivityTracker.recentlySawAppCall()) {
                suppressingAppCallTelephony = true
            }
            publish(state, phoneNumber)
            return
        }

        if (!shouldDebounceAmbiguousTelephony(state, phoneNumber)) {
            cancelPendingAmbiguousTelephony()
            publish(state, phoneNumber)
            return
        }

        cancelPendingAmbiguousTelephony()
        val pending = Runnable {
            pendingAmbiguousTelephonyState = null
            publish(state, phoneNumber)
        }
        pendingAmbiguousTelephonyState = pending
        mainHandler.postDelayed(pending, AMBIGUOUS_TELEPHONY_DEBOUNCE_MS)
        DebugEventLog.record("call", "Debouncing ambiguous SIM call state ${state.name}; waiting for app-call notification.")
    }

    private fun shouldDebounceAmbiguousTelephony(state: PhoneCallState, phoneNumber: String?): Boolean {
        if (phoneNumber?.isNotBlank() == true) return false
        if (CallSessionContext.currentOutgoing() != null) return false
        return state == PhoneCallState.PHONE_CALL_STATE_RINGING ||
            state == PhoneCallState.PHONE_CALL_STATE_OFFHOOK
    }

    private fun cancelPendingAmbiguousTelephony() {
        pendingAmbiguousTelephonyState?.let { mainHandler.removeCallbacks(it) }
        pendingAmbiguousTelephonyState = null
    }

    private fun publish(state: PhoneCallState, phoneNumber: String?) {
        val activeAppCall = AppCallActivityTracker.activeRecent()
        if (state != PhoneCallState.PHONE_CALL_STATE_IDLE && activeAppCall != null) {
            if (state != lastState) {
                DebugEventLog.record(
                    "call",
                    "Suppressed SIM call metadata while ${activeAppCall.appName.ifBlank { activeAppCall.packageName }} " +
                        "app-call notification is active.",
                )
            }
            suppressingAppCallTelephony = true
            lastState = state
            return
        }
        if (
            state == PhoneCallState.PHONE_CALL_STATE_IDLE &&
            suppressingAppCallTelephony &&
            AppCallActivityTracker.recentlySawAppCall()
        ) {
            suppressingAppCallTelephony = false
            lastState = state
            lastDirection = CallDirection.CALL_DIRECTION_UNSPECIFIED
            lastCallerId = ""
            CallSessionContext.clearOutgoing()
            DebugEventLog.record("call", "Suppressed SIM idle metadata after app-call notification ended.")
            return
        }
        if (state == lastState) return
        lastState = state
        val outgoingContext = CallSessionContext.currentOutgoing()
        val callerId = phoneNumber.orEmpty()
        if (callerId.isNotBlank()) {
            lastCallerId = callerId
        }
        val direction = directionFor(state, callerId, outgoingContext)
        if (direction != CallDirection.CALL_DIRECTION_UNSPECIFIED) {
            lastDirection = direction
        }
        val activeSim = activeVoiceSubscription()
        val effectiveCallerId = callerId.ifBlank { outgoingContext?.phoneNumber.orEmpty() }
        val effectiveSimSlot = outgoingContext?.simSlot
            ?: activeSim?.let { it.simSlotIndex + 1 }?.takeIf { it > 0 }
            ?: 0
        val effectiveSubscriptionId = outgoingContext?.subscriptionId ?: activeSim?.subscriptionId ?: -1
        val effectiveCarrier = outgoingContext?.carrierName ?: activeSim?.carrierName?.toString().orEmpty()
        val detail = detailFor(state, effectiveCallerId, direction)
        val event = CallStateEvent.newBuilder()
            .setEventId(UUID.randomUUID().toString())
            .setState(state)
            .setOccurredAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .setIncomingNumberAvailable(effectiveCallerId.isNotBlank())
            .setMaskedNumberHint(maskNumber(effectiveCallerId))
            .setDetail(detail)
            .build()
        CallStateBridge.publish(event)
        CallStateBridge.publishMetadata(
            CallMetadataEvent.newBuilder()
                .setEventId(event.eventId)
                .setState(state)
                .setDirection(direction)
                .setSourceType(CallSourceType.CALL_SOURCE_TYPE_SIM_TELEPHONY)
                .setSourceAppPackage("android.telephony")
                .setSourceAppLabel("SIM call")
                .setCallerIdAvailable(effectiveCallerId.isNotBlank())
                .setCallerId(effectiveCallerId)
                .setMaskedCallerId(maskNumber(effectiveCallerId.ifBlank { lastCallerId }))
                .setDisplayName("")
                .setSimSlot(effectiveSimSlot)
                .setSubscriptionId(effectiveSubscriptionId)
                .setCarrierName(effectiveCarrier)
                .setPhoneAccountId("")
                .setVideoCall(false)
                .setActiveAudioRoute(activeAudioRoute())
                .setDetail(detail)
                .setOccurredAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
                .build(),
        )
        DebugEventLog.record("call", detail)
        if (state == PhoneCallState.PHONE_CALL_STATE_IDLE) {
            lastDirection = CallDirection.CALL_DIRECTION_UNSPECIFIED
            lastCallerId = ""
            CallSessionContext.clearOutgoing()
        }
    }

    private fun directionFor(
        state: PhoneCallState,
        callerId: String,
        outgoingContext: PendingOutgoingCallContext?,
    ): CallDirection {
        return when (state) {
            PhoneCallState.PHONE_CALL_STATE_RINGING -> CallDirection.CALL_DIRECTION_INCOMING
            PhoneCallState.PHONE_CALL_STATE_OFFHOOK -> when {
                outgoingContext != null -> CallDirection.CALL_DIRECTION_OUTGOING
                lastDirection == CallDirection.CALL_DIRECTION_INCOMING -> CallDirection.CALL_DIRECTION_INCOMING
                callerId.isNotBlank() -> CallDirection.CALL_DIRECTION_INCOMING
                else -> CallDirection.CALL_DIRECTION_OUTGOING
            }
            PhoneCallState.PHONE_CALL_STATE_IDLE -> lastDirection
            else -> CallDirection.CALL_DIRECTION_UNSPECIFIED
        }
    }

    private fun detailFor(state: PhoneCallState, callerId: String, direction: CallDirection): String {
        val callerDetail = if (callerId.isBlank()) {
            "caller ID unavailable; grant READ_CALL_LOG or use default-dialer/calling integration if Android still withholds it"
        } else {
            "caller ${maskNumber(callerId)}"
        }
        val directionDetail = when (direction) {
            CallDirection.CALL_DIRECTION_OUTGOING -> "outgoing"
            CallDirection.CALL_DIRECTION_INCOMING -> "incoming"
            else -> "unknown direction"
        }
        return when (state) {
            PhoneCallState.PHONE_CALL_STATE_IDLE -> "Call state idle; $directionDetail; $callerDetail"
            PhoneCallState.PHONE_CALL_STATE_RINGING -> "Incoming SIM call ringing; $callerDetail"
            PhoneCallState.PHONE_CALL_STATE_OFFHOOK -> "SIM call active or dialing; $directionDetail; $callerDetail"
            else -> "Unknown call state; $directionDetail; $callerDetail"
        }
    }

    private fun activeVoiceSubscription(): SubscriptionInfo? {
        if (ContextCompat.checkSelfPermission(appContext, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            return null
        }
        return runCatching {
            @Suppress("MissingPermission")
            val subscriptions = subscriptionManager.activeSubscriptionInfoList.orEmpty()
            val defaultVoiceSubId = SubscriptionManager.getDefaultVoiceSubscriptionId()
            subscriptions.firstOrNull { it.subscriptionId == defaultVoiceSubId }
                ?: subscriptions.sortedBy { it.simSlotIndex }.firstOrNull()
        }.getOrNull()
    }

    private fun activeAudioRoute(): PhoneAudioRouteType {
        return when {
            audioManager.isBluetoothScoOn -> PhoneAudioRouteType.PHONE_AUDIO_ROUTE_TYPE_BLUETOOTH
            wiredHeadsetOn() -> PhoneAudioRouteType.PHONE_AUDIO_ROUTE_TYPE_WIRED_HEADSET
            speakerphoneOn() -> PhoneAudioRouteType.PHONE_AUDIO_ROUTE_TYPE_SPEAKER
            else -> PhoneAudioRouteType.PHONE_AUDIO_ROUTE_TYPE_PHONE_DEFAULT
        }
    }

    @Suppress("DEPRECATION")
    private fun wiredHeadsetOn(): Boolean = audioManager.isWiredHeadsetOn

    @Suppress("DEPRECATION")
    private fun speakerphoneOn(): Boolean = audioManager.isSpeakerphoneOn

    private fun maskNumber(phoneNumber: String?): String {
        val digits = phoneNumber?.filter { it.isDigit() }.orEmpty()
        if (digits.length < 4) return ""
        return "ending ${digits.takeLast(4)}"
    }

    private companion object {
        const val AMBIGUOUS_TELEPHONY_DEBOUNCE_MS = 1_100L
    }
}
