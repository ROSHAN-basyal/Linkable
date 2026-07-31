package com.linkable.calls

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.os.Build
import android.telephony.SubscriptionInfo
import android.telephony.SubscriptionManager
import androidx.core.content.ContextCompat
import com.linkable.protocol.v1.PhoneAudioRouteType
import com.linkable.protocol.v1.PhoneCapabilitySnapshot
import com.linkable.protocol.v1.PhoneRingerMode
import com.linkable.protocol.v1.SimStatus
import com.linkable.protocol.v1.TelephonyDiagnosticsRequest
import com.linkable.protocol.v1.TelephonyDiagnosticsResult
import com.linkable.protocol.v1.TelephonyPermissionStatus
import com.linkable.protocol.v1.Timestamp
import java.util.UUID

class TelephonyDiagnosticsProvider(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val subscriptionManager = appContext.getSystemService(SubscriptionManager::class.java)
    private val audioManager = appContext.getSystemService(AudioManager::class.java)

    fun snapshot(request: TelephonyDiagnosticsRequest): TelephonyDiagnosticsResult {
        val permissions = permissions()
        val sims = activeSubscriptions().map { it.toSimStatus() }
        val capabilitySnapshot = phoneCapabilitySnapshot(permissions, sims)
        val detail = buildString {
            append("permissions: read_phone_state=${permissions.readPhoneStateGranted}, ")
            append("read_call_log=${permissions.readCallLogGranted}, ")
            append("answer_calls=${permissions.answerPhoneCallsGranted}, call_phone=${permissions.callPhoneGranted}; ")
            if (sims.isEmpty()) {
                append("no active SIM subscriptions visible")
            } else {
                append(
                    sims.joinToString("; ") { sim ->
                        "SIM ${sim.simSlot}: subId=${sim.subscriptionId}, carrier=${sim.carrierName}, " +
                            "voiceDefault=${sim.defaultVoice}, dataDefault=${sim.defaultData}"
                    },
                )
            }
        }
        return TelephonyDiagnosticsResult.newBuilder()
            .setRequestId(request.requestId)
            .setPermissions(permissions)
            .addAllSims(sims)
            .setCallStateMirroringSupported(permissions.readPhoneStateGranted)
            .setCallControlSupported(permissions.answerPhoneCallsGranted && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            .setDirectDialSupported(permissions.callPhoneGranted)
            .setAndroidVersion("Android ${Build.VERSION.RELEASE} API ${Build.VERSION.SDK_INT}")
            .setDeviceModel("${Build.MANUFACTURER} ${Build.MODEL}".trim())
            .setDetail(detail)
            .setGeneratedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .setPhoneCapabilities(capabilitySnapshot)
            .build()
    }

    fun summary(): String {
        val diagnostics = snapshot(
            TelephonyDiagnosticsRequest.newBuilder()
                .setRequestId("local")
                .setRequestedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
                .build(),
        )
        return "${diagnostics.detail}\n${diagnostics.phoneCapabilities.detail}"
    }

    fun capabilitySnapshot(): PhoneCapabilitySnapshot {
        val permissions = permissions()
        return phoneCapabilitySnapshot(permissions, activeSubscriptions().map { it.toSimStatus() })
    }

    private fun permissions(): TelephonyPermissionStatus {
        return TelephonyPermissionStatus.newBuilder()
            .setReadPhoneStateGranted(hasPermission(Manifest.permission.READ_PHONE_STATE))
            .setAnswerPhoneCallsGranted(
                Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
                    hasPermission(Manifest.permission.ANSWER_PHONE_CALLS),
            )
            .setCallPhoneGranted(hasPermission(Manifest.permission.CALL_PHONE))
            .setReadCallLogGranted(hasPermission(Manifest.permission.READ_CALL_LOG))
            .build()
    }

    private fun phoneCapabilitySnapshot(
        permissions: TelephonyPermissionStatus,
        sims: List<SimStatus>,
    ): PhoneCapabilitySnapshot {
        val ringerMode = when (audioManager.ringerMode) {
            AudioManager.RINGER_MODE_SILENT -> PhoneRingerMode.PHONE_RINGER_MODE_SILENT
            AudioManager.RINGER_MODE_VIBRATE -> PhoneRingerMode.PHONE_RINGER_MODE_VIBRATE
            AudioManager.RINGER_MODE_NORMAL -> PhoneRingerMode.PHONE_RINGER_MODE_NORMAL
            else -> PhoneRingerMode.PHONE_RINGER_MODE_UNSPECIFIED
        }
        val activeRoute = activeAudioRoute()
        val callerIdSupported = permissions.readPhoneStateGranted && permissions.readCallLogGranted
        val detail = buildString {
            append("sim_count=${sims.size}; ")
            append("ringer=${PhoneRingerMode.forNumber(ringerMode.number).name}; ")
            append("route=${PhoneAudioRouteType.forNumber(activeRoute.number).name}; ")
            append("caller_id_supported=$callerIdSupported; ")
            append("lan_call_audio_supported=false; bluetooth_call_audio_recommended=true")
        }
        return PhoneCapabilitySnapshot.newBuilder()
            .setSnapshotId(UUID.randomUUID().toString())
            .setPermissions(permissions)
            .setSimCount(sims.size)
            .addAllSims(sims)
            .setRingerMode(ringerMode)
            .setRingVolume(audioManager.getStreamVolume(AudioManager.STREAM_RING))
            .setRingVolumeMax(audioManager.getStreamMaxVolume(AudioManager.STREAM_RING))
            .setVoiceCallVolume(audioManager.getStreamVolume(AudioManager.STREAM_VOICE_CALL))
            .setVoiceCallVolumeMax(audioManager.getStreamMaxVolume(AudioManager.STREAM_VOICE_CALL))
            .setSpeakerphoneOn(speakerphoneOn())
            .setBluetoothScoAvailable(audioManager.isBluetoothScoAvailableOffCall)
            .setWiredHeadsetConnected(wiredHeadsetOn())
            .setActiveAudioRoute(activeRoute)
            .setCallStateMirroringSupported(permissions.readPhoneStateGranted)
            .setCallerIdSupported(callerIdSupported)
            .setCallControlSupported(permissions.answerPhoneCallsGranted && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            .setDirectDialSupported(permissions.callPhoneGranted)
            .setLanCallAudioSupported(false)
            .setBluetoothCallAudioRecommended(true)
            .setDetail(detail)
            .setGeneratedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun activeSubscriptions(): List<SubscriptionInfo> {
        if (!hasPermission(Manifest.permission.READ_PHONE_STATE)) return emptyList()
        return runCatching {
            @Suppress("MissingPermission")
            subscriptionManager.activeSubscriptionInfoList.orEmpty().sortedBy { it.simSlotIndex }
        }.getOrDefault(emptyList())
    }

    private fun SubscriptionInfo.toSimStatus(): SimStatus {
        val slotOneBased = simSlotIndex + 1
        return SimStatus.newBuilder()
            .setSimSlot(slotOneBased.takeIf { it > 0 } ?: 0)
            .setSubscriptionId(subscriptionId)
            .setCarrierName(carrierName?.toString().orEmpty())
            .setDisplayName(displayName?.toString().orEmpty())
            .setActive(simSlotIndex >= 0)
            .setDefaultVoice(SubscriptionManager.getDefaultVoiceSubscriptionId() == subscriptionId)
            .setDefaultData(SubscriptionManager.getDefaultDataSubscriptionId() == subscriptionId)
            .setDefaultSms(SubscriptionManager.getDefaultSmsSubscriptionId() == subscriptionId)
            .build()
    }

    private fun hasPermission(permission: String): Boolean {
        return ContextCompat.checkSelfPermission(appContext, permission) == PackageManager.PERMISSION_GRANTED
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
}
